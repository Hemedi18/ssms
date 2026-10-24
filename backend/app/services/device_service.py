import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List, Dict, Any, Set
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_, desc, func

from app.core.config import settings
from app.core.logging import logger
from app.core.security import generate_device_token, generate_pairing_code
from app.models.device import GatewayDevice, PairingCode
from app.models.message import Message, MessageEvent
from app.schemas.device import (
    DevicePairRequest,
    DeviceHeartbeatRequest,
    DeviceJobResponse,
    DeviceSendResultRequest,
)
from app.services.webhook_service import queue_event
from app.services.audit_service import record_audit_event
from app.services.bundle_service import refund_credits


# ---------------------------------------------------------------------------
# Emergency Kill-Switch State
# ---------------------------------------------------------------------------
_kill_switch_global: bool = False
_kill_switch_tenants: Set[str] = set()


def set_kill_switch(enabled: bool, tenant_id: Optional[str] = None) -> Dict[str, Any]:
    global _kill_switch_global, _kill_switch_tenants
    if tenant_id:
        if enabled:
            _kill_switch_tenants.add(tenant_id)
        else:
            _kill_switch_tenants.discard(tenant_id)
    else:
        _kill_switch_global = enabled
    return get_kill_switch_status()


def get_kill_switch_status() -> Dict[str, Any]:
    return {
        "global_paused": _kill_switch_global,
        "paused_tenants": list(_kill_switch_tenants),
    }


def is_leasing_paused(tenant_id: Optional[str] = None) -> bool:
    if _kill_switch_global:
        return True
    if tenant_id and tenant_id in _kill_switch_tenants:
        return True
    return False


# ---------------------------------------------------------------------------
# Pairing & Heartbeat
# ---------------------------------------------------------------------------
def create_pairing_code(
    db: Session,
    device_name: str = "Android Gateway Device",
    expires_in_seconds: int = 600,
    tenant_id: Optional[str] = None,
) -> PairingCode:
    """Creates a temporary, one-time pairing code for phone registration."""
    code_str = generate_pairing_code()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)

    pairing_code = PairingCode(
        tenant_id=tenant_id,
        code=code_str,
        device_name=device_name,
        expires_at=expires_at,
    )
    db.add(pairing_code)
    db.commit()
    db.refresh(pairing_code)
    logger.info(f"Created pairing code for '{device_name}' valid until {expires_at.isoformat()}")
    return pairing_code


def pair_device(
    db: Session, req: DevicePairRequest, ip_address: Optional[str] = None
) -> Tuple[GatewayDevice, str]:
    """Exchanges an active pairing code for persistent device credentials."""
    clean_code = req.pairing_code.strip().upper()
    now = datetime.now(timezone.utc)

    pairing_code = db.scalar(
        select(PairingCode).where(
            and_(
                PairingCode.code == clean_code,
                PairingCode.is_used == False,
                PairingCode.expires_at > now,
            )
        )
    )

    if not pairing_code:
        raise ValueError("Invalid or expired pairing code.")

    # Invalidate pairing code
    pairing_code.is_used = True

    # Generate device token
    raw_token, token_hash = generate_device_token()

    device = GatewayDevice(
        tenant_id=req.tenant_id or pairing_code.tenant_id,
        name=req.device_name or pairing_code.device_name,
        model=req.model,
        os_version=req.os_version,
        app_version=req.app_version,
        device_token_hash=token_hash,
        is_online=True,
        last_seen_at=now,
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    record_audit_event(
        db,
        action="device.pair",
        actor_type="device",
        actor_id=device.id,
        details={"name": device.name, "model": device.model},
        ip_address=ip_address,
    )

    queue_event(
        db,
        event_type="device.online",
        data={"device_id": device.id, "name": device.name, "status": "online"},
    )

    logger.info(f"Device paired successfully: [{device.id}] {device.name}")
    return device, raw_token


def update_heartbeat(
    db: Session, device: GatewayDevice, req: DeviceHeartbeatRequest
) -> GatewayDevice:
    """Updates device diagnostics, dual-SIM telemetry, and online/offline status."""
    was_offline = not device.is_online

    device.sim_ready = req.sim_ready
    if req.phone_number:
        device.phone_number = req.phone_number
    if req.carrier_name:
        device.carrier_name = req.carrier_name
    if req.network_type:
        device.network_type = req.network_type
    if req.signal_level is not None:
        device.signal_level = req.signal_level
    if req.battery_level is not None:
        device.battery_level = req.battery_level
    if req.sim_slots is not None:
        device.sim_slots_telemetry = [s.model_dump() for s in req.sim_slots]

    device.is_online = True
    device.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(device)

    if was_offline:
        queue_event(
            db,
            event_type="device.online",
            data={"device_id": device.id, "name": device.name, "status": "online"},
        )

    return device


# ---------------------------------------------------------------------------
# Smart SIM Slot Matcher & Rolling Throttle Window
# ---------------------------------------------------------------------------
def _resolve_best_sim_slot(device: GatewayDevice, message: Message) -> Optional[int]:
    """
    Selects the best physical SIM slot (0 or 1) on the handset based on On-Net matching.
    """
    if message.sim_slot is not None:
        return message.sim_slot

    mno = message.detected_mno or "UNKNOWN"
    if mno == "UNKNOWN" or mno == "INTERNATIONAL":
        return 0

    slots = device.sim_slots_telemetry or []
    mno_carrier_keywords = {
        "VODACOM_TZ": ["vodacom", "voda"],
        "AIRTEL_TZ": ["airtel"],
        "YAS_TIGO_TZ": ["tigo", "yas", "zantel"],
        "HALOTEL_TZ": ["halotel", "halo"],
        "TTCL_TZ": ["ttcl"],
    }
    keywords = mno_carrier_keywords.get(mno, [])

    for slot_data in slots:
        carrier = (slot_data.get("carrier") or "").lower()
        if any(kw in carrier for kw in keywords):
            return slot_data.get("slot", 0)

    # Fallback to device's primary carrier if matching
    primary_carrier = (device.carrier_name or "").lower()
    if any(kw in primary_carrier for kw in keywords):
        return 0

    return 0


# ---------------------------------------------------------------------------
# Concurrency-Safe Job Leasing with Priority Queue & Throttle Limits
# ---------------------------------------------------------------------------
def get_next_job(db: Session, device: GatewayDevice) -> Optional[DeviceJobResponse]:
    """
    Leases the next eligible SMS job to the device:
    - Enforces emergency kill-switch.
    - Matches tenant isolation or shared device pool.
    - Prevents Android OS limit lockup by checking rolling 30-minute throttle limit.
    - Priority queue: orders by Message.priority DESC, Message.created_at ASC.
    - Recovers expired leases automatically.
    """
    if is_leasing_paused(device.tenant_id):
        return None

    now = datetime.now(timezone.utc)

    # 1. Enforce rolling 30-minute rate limit (Android SMS limit safety)
    thirty_mins_ago = now - timedelta(minutes=30)
    rolling_count = db.scalar(
        select(func.count(Message.id)).where(
            and_(
                Message.device_id == device.id,
                Message.status.in_(["dispatched", "sending", "sent"]),
                Message.leased_at != None,
                Message.leased_at >= thirty_mins_ago,
            )
        )
    ) or 0

    max_limit = device.max_sms_per_30_min or 28
    if rolling_count >= max_limit:
        logger.warning(
            f"Device [{device.id}] reached 30m throttle limit ({rolling_count}/{max_limit} SMS). Pausing lease."
        )
        return None

    # 2. Build tenant criteria:
    # If device is assigned to tenant and is not shared pool -> only that tenant's messages.
    # If device is shared pool -> can lease messages from tenant or shared pool.
    tenant_filter = []
    if device.tenant_id and not device.is_shared_pool:
        tenant_filter.append(Message.tenant_id == device.tenant_id)

    # Status filter: queued or expired dispatched lease
    status_filter = or_(
        Message.status == "queued",
        and_(
            Message.status == "dispatched",
            Message.lease_expires_at != None,
            Message.lease_expires_at < now,
        ),
    )

    query = (
        select(Message)
        .where(status_filter)
        .where(
            or_(
                Message.scheduled_for == None,
                Message.scheduled_for <= now,
            )
        )
    )
    if tenant_filter:
        query = query.where(*tenant_filter)

    # Concurrency safe: Order by priority DESC, created_at ASC
    query = query.order_by(desc(Message.priority), Message.created_at).limit(1)

    # If Postgres, use FOR UPDATE SKIP LOCKED
    if not settings.DATABASE_URL.startswith("sqlite"):
        try:
            query = query.with_for_update(skip_locked=True)
        except Exception:
            pass

    message = db.scalar(query)
    if not message:
        return None

    # 3. Smart SIM slot resolution
    resolved_slot = _resolve_best_sim_slot(device, message)

    # 4. Acquire lease
    lease_token = secrets.token_hex(16)
    message.status = "dispatched"
    message.device_id = device.id
    message.lease_token = lease_token
    message.leased_at = now
    message.lease_expires_at = now + timedelta(
        seconds=settings.JOB_LEASE_TIMEOUT_SECONDS
    )
    if message.sim_slot is None and resolved_slot is not None:
        message.sim_slot = resolved_slot

    event = MessageEvent(
        message_id=message.id,
        status="dispatched",
        device_id=device.id,
        error_details=f"Job leased by device {device.name} (SimSlot: {message.sim_slot}, Priority: {message.priority})",
    )
    db.add(event)
    db.commit()
    db.refresh(message)

    logger.info(
        f"Leased job [{message.id}] to device [{device.id}] until {message.lease_expires_at}"
    )

    return DeviceJobResponse(
        job_id=message.id,
        message_id=message.id,
        to=message.to,
        body=message.body,
        lease_token=lease_token,
        parts_count=message.parts_count,
        sim_slot=message.sim_slot,
        priority=message.priority,
        encoding=message.encoding,
        created_at=message.created_at,
    )


# ---------------------------------------------------------------------------
# Result Reporting & Auto-Refund on Failure
# ---------------------------------------------------------------------------
def report_send_result(
    db: Session,
    device: GatewayDevice,
    job_id: str,
    req: DeviceSendResultRequest,
) -> Message:
    """Updates message status based on Android SmsManager callbacks and executes auto-refund on failure."""
    message = db.get(Message, job_id)
    if not message:
        raise KeyError(f"Job {job_id} not found")

    now = datetime.now(timezone.utc)
    target_status = req.status

    if target_status == "sent":
        message.status = "sent"
        message.sent_at = req.timestamp or now
        message.error_message = None
        event_type = "sms.sent"
    elif target_status == "delivered":
        message.status = "delivered"
        message.delivered_at = req.timestamp or now
        message.error_message = None
        event_type = "sms.delivered"
    elif target_status == "failed":
        message.status = "failed"
        message.error_message = req.error_message or "SMS transmission failed"
        event_type = "sms.failed"

        # Auto-refund credits to tenant bundle on permanent radio failure
        try:
            refund_credits(
                db,
                credits_to_refund=message.parts_count,
                tenant_id=message.tenant_id,
                message_id=message.id,
                reason=f"Auto-refund: cellular transmission failed ({message.error_message})",
            )
        except Exception as e:
            logger.error(f"Failed to auto-refund failed message {message.id}: {e}")
    else:
        raise ValueError(f"Unsupported result status '{target_status}'")

    # Record event
    event = MessageEvent(
        message_id=message.id,
        status=target_status,
        device_id=device.id,
        error_details=req.error_message,
        event_timestamp=req.timestamp or now,
    )
    db.add(event)
    db.commit()
    db.refresh(message)

    logger.info(
        f"Updated message [{message.id}] status to '{message.status}' from device [{device.id}]"
    )

    # Emit webhook
    queue_event(
        db,
        event_type=event_type,
        data={
            "message_id": message.id,
            "tenant_id": message.tenant_id,
            "to": message.to,
            "status": message.status,
            "device_id": device.id,
            "error_message": message.error_message,
            "sent_at": message.sent_at.isoformat() if message.sent_at else None,
            "delivered_at": message.delivered_at.isoformat() if message.delivered_at else None,
        },
    )

    return message


def check_and_update_offline_devices(db: Session) -> int:
    """Marks devices offline if heartbeat exceeded threshold."""
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=settings.DEVICE_OFFLINE_THRESHOLD_SECONDS
    )
    devices = db.scalars(
        select(GatewayDevice).where(
            and_(
                GatewayDevice.is_online == True,
                or_(
                    GatewayDevice.last_seen_at == None,
                    GatewayDevice.last_seen_at < cutoff,
                ),
            )
        )
    ).all()

    count = 0
    for d in devices:
        d.is_online = False
        queue_event(
            db,
            event_type="device.offline",
            data={"device_id": d.id, "name": d.name, "status": "offline"},
        )
        count += 1

    if count > 0:
        db.commit()
        logger.info(f"Marked {count} gateway devices offline")
    return count
