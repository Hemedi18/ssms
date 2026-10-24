import os
import platform
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc, and_

from app.api.deps import get_db, get_current_admin
from app.core.config import settings
from app.core.security import generate_api_key
from app.models.api_key import ApiKey
from app.models.device import GatewayDevice, PairingCode
from app.models.message import Message, MessageEvent
from app.models.incoming_message import IncomingMessage
from app.models.webhook import WebhookSubscription, WebhookDelivery
from app.models.audit import AuditEvent
from app.services.device_service import create_pairing_code
from app.services.webhook_service import deliver_webhook_sync, queue_event
from app.services.audit_service import record_audit_event

router = APIRouter(prefix="/admin", tags=["Admin Portal"])


# -------------------------------------------------------------
# Schemas
# -------------------------------------------------------------
class ApiKeyCreateAdmin(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    scopes: List[str] = Field(default=["sms:send", "sms:read"])
    rate_limit: int = Field(default=60, ge=1, le=1000)
    expires_in_days: Optional[int] = Field(default=None, ge=1)


class PairingCodeAdminRequest(BaseModel):
    device_name: str = Field(default="Android Phone", min_length=2, max_length=100)
    expires_in_seconds: int = Field(default=600, ge=60, le=3600)


# -------------------------------------------------------------
# 1. Dashboard Aggregated Stats & Charts Data
# -------------------------------------------------------------
@router.get("/stats")
def get_dashboard_stats(
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Returns complete real-time dashboard statistics:
    - Message counts by status
    - Inbound messages count
    - Gateway device online/offline count
    - Webhook health and delivery counts
    - 24-hour and 7-day timeseries data for Chart.js
    - Recipient carrier / network breakdown
    - Recent live activity log
    """
    now = datetime.now(timezone.utc)

    # 1. Message status counts
    total_msgs = db.scalar(select(func.count(Message.id))) or 0
    queued_msgs = db.scalar(select(func.count(Message.id)).where(Message.status == "queued")) or 0
    sending_msgs = db.scalar(select(func.count(Message.id)).where(Message.status.in_(["dispatched", "sending"]))) or 0
    sent_msgs = db.scalar(select(func.count(Message.id)).where(Message.status == "sent")) or 0
    delivered_msgs = db.scalar(select(func.count(Message.id)).where(Message.status == "delivered")) or 0
    failed_msgs = db.scalar(select(func.count(Message.id)).where(Message.status == "failed")) or 0

    # 2. Inbound messages count
    incoming_msgs = db.scalar(select(func.count(IncomingMessage.id))) or 0

    # 3. Device counts
    total_devices = db.scalar(select(func.count(GatewayDevice.id)).where(GatewayDevice.is_revoked == False)) or 0
    online_devices = db.scalar(
        select(func.count(GatewayDevice.id)).where(
            and_(GatewayDevice.is_online == True, GatewayDevice.is_revoked == False)
        )
    ) or 0
    offline_devices = max(0, total_devices - online_devices)

    # 4. Webhook deliveries
    total_webhooks = db.scalar(select(func.count(WebhookSubscription.id)).where(WebhookSubscription.is_active == True)) or 0
    delivered_webhooks = db.scalar(select(func.count(WebhookDelivery.id)).where(WebhookDelivery.status == "delivered")) or 0
    failed_webhooks = db.scalar(select(func.count(WebhookDelivery.id)).where(WebhookDelivery.status == "failed")) or 0

    # 5. Timeseries for Chart.js (Last 12 hours hourly slots)
    timeseries_labels = []
    timeseries_sent = []
    timeseries_delivered = []
    timeseries_failed = []
    timeseries_received = []

    for i in range(11, -1, -1):
        slot_start = now - timedelta(hours=i + 1)
        slot_end = now - timedelta(hours=i)
        label = slot_end.strftime("%H:00")
        timeseries_labels.append(label)

        s_count = db.scalar(
            select(func.count(Message.id)).where(
                and_(Message.created_at >= slot_start, Message.created_at < slot_end)
            )
        ) or 0
        d_count = db.scalar(
            select(func.count(Message.id)).where(
                and_(
                    Message.status == "delivered",
                    Message.updated_at >= slot_start,
                    Message.updated_at < slot_end,
                )
            )
        ) or 0
        f_count = db.scalar(
            select(func.count(Message.id)).where(
                and_(
                    Message.status == "failed",
                    Message.updated_at >= slot_start,
                    Message.updated_at < slot_end,
                )
            )
        ) or 0
        r_count = db.scalar(
            select(func.count(IncomingMessage.id)).where(
                and_(
                    IncomingMessage.created_at >= slot_start,
                    IncomingMessage.created_at < slot_end,
                )
            )
        ) or 0

        timeseries_sent.append(s_count)
        timeseries_delivered.append(d_count)
        timeseries_failed.append(f_count)
        timeseries_received.append(r_count)

    # 6. Carrier breakdown based on destination prefix
    # E.g., Tanzania prefixes: Vodacom (74, 75, 76), Airtel (68, 69, 78), Tigo (65, 67, 71), Halotel (61, 62)
    messages_sample = db.scalars(select(Message.to).limit(200)).all()
    carriers = {"Vodacom": 0, "Airtel": 0, "Tigo": 0, "Halotel": 0, "Other": 0}
    for phone in messages_sample:
        p = phone.replace("+255", "").replace("0", "", 1)
        if any(p.startswith(pref) for pref in ["74", "75", "76"]):
            carriers["Vodacom"] += 1
        elif any(p.startswith(pref) for pref in ["68", "69", "78"]):
            carriers["Airtel"] += 1
        elif any(p.startswith(pref) for pref in ["65", "67", "71"]):
            carriers["Tigo"] += 1
        elif any(p.startswith(pref) for pref in ["61", "62"]):
            carriers["Halotel"] += 1
        else:
            carriers["Other"] += 1

    # 7. Recent activity log (latest 15 events)
    recent_audits = db.scalars(
        select(AuditEvent).order_by(desc(AuditEvent.created_at)).limit(15)
    ).all()
    activities = [
        {
            "id": a.id,
            "action": a.action,
            "actor": f"{a.actor_type}:{a.actor_id or 'sys'}",
            "details": a.details,
            "created_at": a.created_at.isoformat(),
        }
        for a in recent_audits
    ]

    # Calculate success rate
    completed = delivered_msgs + sent_msgs + failed_msgs
    success_rate = round(((delivered_msgs + sent_msgs) / completed * 100), 1) if completed > 0 else 100.0

    return {
        "summary": {
            "total_messages": total_msgs,
            "queued": queued_msgs,
            "sending": sending_msgs,
            "sent": sent_msgs,
            "delivered": delivered_msgs,
            "failed": failed_msgs,
            "incoming_messages": incoming_msgs,
            "success_rate_percent": success_rate,
            "devices": {
                "total": total_devices,
                "online": online_devices,
                "offline": offline_devices,
            },
            "webhooks": {
                "total": total_webhooks,
                "delivered": delivered_webhooks,
                "failed": failed_webhooks,
            },
        },
        "charts": {
            "timeseries": {
                "labels": timeseries_labels,
                "sent": timeseries_sent,
                "delivered": timeseries_delivered,
                "failed": timeseries_failed,
                "received": timeseries_received,
            },
            "status_donut": {
                "labels": ["Delivered", "Sent", "Queued", "Failed"],
                "data": [delivered_msgs, sent_msgs, queued_msgs, failed_msgs],
            },
            "carriers": carriers,
        },
        "recent_activities": activities,
    }


# -------------------------------------------------------------
# 2. API Key Management
# -------------------------------------------------------------
@router.get("/api-keys")
def list_admin_api_keys(
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Lists all created client API keys with masked token secrets."""
    keys = db.scalars(select(ApiKey).order_by(desc(ApiKey.created_at))).all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "key_prefix": k.key_prefix,
            "scopes": k.scopes,
            "is_active": k.is_active,
            "rate_limit": k.rate_limit,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
        }
        for k in keys
    ]


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
def create_admin_api_key(
    payload: ApiKeyCreateAdmin,
    request: Request,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Creates a new client API key and returns the full secret token ONCE.
    """
    raw_key, prefix, key_hash = generate_api_key(prefix="sms_live_")
    expires_at = None
    if payload.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)

    api_key = ApiKey(
        name=payload.name.strip(),
        key_hash=key_hash,
        key_prefix=prefix,
        scopes=payload.scopes,
        rate_limit=payload.rate_limit,
        expires_at=expires_at,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    client_ip = request.client.host if request.client else None
    record_audit_event(
        db,
        action="api_key.create",
        actor_type="admin",
        actor_id=admin.get("sub", "admin"),
        details={"name": api_key.name, "prefix": prefix, "scopes": api_key.scopes},
        ip_address=client_ip,
    )

    return {
        "id": api_key.id,
        "name": api_key.name,
        "raw_key": raw_key,
        "key_prefix": prefix,
        "scopes": api_key.scopes,
        "rate_limit": api_key.rate_limit,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "created_at": api_key.created_at.isoformat(),
        "message": "Copy this API key now! It will not be shown again.",
    }


@router.delete("/api-keys/{key_id}")
def revoke_admin_api_key(
    key_id: str,
    request: Request,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Revokes an API key."""
    key = db.get(ApiKey, key_id)
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    key.is_active = False
    db.commit()

    client_ip = request.client.host if request.client else None
    record_audit_event(
        db,
        action="api_key.revoke",
        actor_type="admin",
        actor_id=admin.get("sub", "admin"),
        details={"key_id": key_id, "name": key.name},
        ip_address=client_ip,
    )
    return {"status": "success", "message": f"API key '{key.name}' deactivated."}


# -------------------------------------------------------------
# 3. Device Management & Pairing Code Generation
# -------------------------------------------------------------
@router.post("/devices/pairing-code")
def generate_device_pairing_code(
    payload: PairingCodeAdminRequest,
    request: Request,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Generates a fresh 8-character pairing code for setting up the Android SMS Gateway mobile app.
    """
    pairing = create_pairing_code(
        db,
        device_name=payload.device_name,
        expires_in_seconds=payload.expires_in_seconds,
    )
    client_ip = request.client.host if request.client else None
    record_audit_event(
        db,
        action="device.pairing_code.create",
        actor_type="admin",
        actor_id=admin.get("sub", "admin"),
        details={"code": pairing.code, "device_name": pairing.device_name},
        ip_address=client_ip,
    )
    return {
        "code": pairing.code,
        "device_name": pairing.device_name,
        "expires_at": pairing.expires_at.isoformat(),
        "expires_in_seconds": payload.expires_in_seconds,
    }


@router.post("/devices/{device_id}/ping")
def ping_device(
    device_id: str,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Checks device status and last heartbeat timestamp."""
    device = db.get(GatewayDevice, device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return {
        "device_id": device.id,
        "name": device.name,
        "is_online": device.is_online,
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
        "battery_level": device.battery_level,
        "signal_level": device.signal_level,
        "carrier_name": device.carrier_name,
    }


# -------------------------------------------------------------
# 4. Webhook Test Ping
# -------------------------------------------------------------
@router.post("/webhooks/{webhook_id}/test")
def test_webhook_endpoint(
    webhook_id: str,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Sends an immediate test ping event to the specified webhook subscription."""
    sub = db.get(WebhookSubscription, webhook_id)
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")

    deliveries = queue_event(
        db,
        event_type="test.ping",
        data={
            "message": "Test ping from SIM SMS Gateway Admin Dashboard",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "admin": admin.get("sub", "admin"),
        },
    )
    # Deliver synchronously for immediate test feedback
    if deliveries:
        delivery = deliveries[0]
        success = deliver_webhook_sync(db, delivery)
        return {
            "status": "delivered" if success else "failed",
            "http_status": delivery.response_status_code,
            "error": delivery.error_message,
            "response_body": delivery.response_body[:200] if delivery.response_body else None,
        }
    return {"status": "queued"}


# -------------------------------------------------------------
# 5. System Health & Environment Info
# -------------------------------------------------------------
@router.get("/system")
def get_system_diagnostics(
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Returns runtime diagnostic information about the server and database."""
    db_ok = True
    try:
        db.execute(select(1))
    except Exception:
        db_ok = False

    return {
        "project_name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "python_version": sys.version.split(" ")[0],
        "platform": platform.platform(),
        "database_status": "connected" if db_ok else "error",
        "database_url_masked": settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else "sqlite",
        "rate_limit_per_minute": settings.RATE_LIMIT_PER_MINUTE,
        "job_lease_timeout_seconds": settings.JOB_LEASE_TIMEOUT_SECONDS,
        "device_offline_threshold_seconds": settings.DEVICE_OFFLINE_THRESHOLD_SECONDS,
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
    }
