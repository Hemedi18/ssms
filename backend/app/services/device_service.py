import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_, desc

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


def create_pairing_code(
    db: Session,
    device_name: str = "Android Gateway Device",
    expires_in_seconds: int = 600,
) -> PairingCode:
    """Creates a temporary, one-time pairing code for phone registration."""
    code_str = generate_pairing_code()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)

    pairing_code = PairingCode(
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
    """Updates device diagnostics and online/offline status."""
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


def get_next_job(db: Session, device: GatewayDevice) -> Optional[DeviceJobResponse]:
    """
    Leases the next eligible queued SMS job to the device.
    Includes expired lease recovery to safely reclaim abandoned jobs.
    """
    now = datetime.now(timezone.utc)

    # 1. Look for unassigned queued message OR expired lease dispatched message
    stmt = (
        select(Message)
        .where(
            or_(
                Message.status == "queued",
                and_(
                    Message.status == "dispatched",
                    Message.lease_expires_at != None,
                    Message.lease_expires_at < now,
                ),
            )
        )
        .order_by(Message.created_at)
        .limit(1)
    )
    message = db.scalar(stmt)
    if not message:
        return None

    # 2. Acquire lease
    lease_token = secrets.token_hex(16)
    message.status = "dispatched"
    message.device_id = device.id
    message.lease_token = lease_token
    message.leased_at = now
    message.lease_expires_at = now + timedelta(
        seconds=settings.JOB_LEASE_TIMEOUT_SECONDS
    )

    event = MessageEvent(
        message_id=message.id,
        status="dispatched",
        device_id=device.id,
        error_details="Job leased by device",
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
        created_at=message.created_at,
    )


def report_send_result(
    db: Session,
    device: GatewayDevice,
    job_id: str,
    req: DeviceSendResultRequest,
) -> Message:
    """Updates message status based on Android SmsManager callbacks."""
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
