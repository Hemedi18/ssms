import os
import platform
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc, and_, or_

from app.api.deps import get_db, get_current_admin, require_role
from app.core.config import settings
from app.core.security import generate_api_key, hash_password
from app.models.api_key import ApiKey
from app.models.device import GatewayDevice, PairingCode
from app.models.message import Message, MessageEvent
from app.models.incoming_message import IncomingMessage
from app.models.webhook import WebhookSubscription, WebhookDelivery
from app.models.audit import AuditEvent
from app.models.tenant import Tenant, User
from app.models.credit_transaction import CreditTransaction
from app.models.dnd_and_moderation import DndBlacklist, ContentModerationRule
from app.services.device_service import (
    create_pairing_code,
    set_kill_switch,
    get_kill_switch_status,
)
from app.services.webhook_service import deliver_webhook_sync, queue_event
from app.services.audit_service import record_audit_event
from app.services.bundle_service import (
    get_bundle_summary,
    topup_bundle,
    list_credit_transactions,
)
from app.services.message_service import modify_message, batch_action_messages
from app.schemas.message import (
    MessageResponse,
    MessageModifyRequest,
    BatchActionRequest,
    BatchActionResponse,
)
from app.schemas.admin_ext import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    UserCreate,
    UserResponse,
    DndBlacklistCreate,
    DndBlacklistResponse,
    ModerationRuleCreate,
    ModerationRuleResponse,
    KillSwitchRequest,
    KillSwitchResponse,
)

router = APIRouter(prefix="/admin", tags=["Admin Portal"])


# -------------------------------------------------------------
# Schemas
# -------------------------------------------------------------
class ApiKeyCreateAdmin(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    scopes: List[str] = Field(default=["sms:send", "sms:read"])
    rate_limit: int = Field(default=60, ge=1, le=1000)
    expires_in_days: Optional[int] = Field(default=None, ge=1)
    tenant_id: Optional[str] = None
    allowed_ips: Optional[str] = None


class PairingCodeAdminRequest(BaseModel):
    device_name: str = Field(default="Android Phone", min_length=2, max_length=100)
    expires_in_seconds: int = Field(default=600, ge=60, le=3600)
    tenant_id: Optional[str] = None


class BundleTopupRequest(BaseModel):
    credits: int = Field(..., ge=1, le=1000000, description="SMS credits to add")
    extend_days: Optional[int] = Field(default=30, ge=1, le=365, description="Days to extend expiration")
    plan_name: Optional[str] = Field(default=None, max_length=100)
    tenant_id: Optional[str] = None


# -------------------------------------------------------------
# 1. Dashboard Aggregated Stats & Charts Data
# -------------------------------------------------------------
@router.get("/stats")
def get_dashboard_stats(
    tenant_id: Optional[str] = None,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Returns complete real-time dashboard statistics:
    - Message counts by status (including pending_approval, scheduled)
    - Tanzania MNO network breakdown
    - Device and SIM health
    - Kill-switch state
    - Timeseries for Chart.js
    """
    effective_tenant_id = admin.get("tenant_id") or tenant_id

    # Base query filters
    msg_filter = []
    if effective_tenant_id:
        msg_filter.append(Message.tenant_id == effective_tenant_id)

    def _count_status(st: str) -> int:
        q = select(func.count(Message.id)).where(Message.status == st)
        if msg_filter:
            q = q.where(*msg_filter)
        return db.scalar(q) or 0

    total_msgs = db.scalar(
        select(func.count(Message.id)).where(*msg_filter) if msg_filter else select(func.count(Message.id))
    ) or 0

    pending_approval = _count_status("pending_approval")
    scheduled_msgs = _count_status("scheduled")
    queued_msgs = _count_status("queued")
    sending_msgs = db.scalar(
        select(func.count(Message.id))
        .where(Message.status.in_(["dispatched", "sending"]))
        .where(*msg_filter) if msg_filter else select(func.count(Message.id)).where(Message.status.in_(["dispatched", "sending"]))
    ) or 0
    sent_msgs = _count_status("sent")
    delivered_msgs = _count_status("delivered")
    failed_msgs = _count_status("failed")
    rejected_msgs = _count_status("rejected")

    # Inbound messages
    inbound_q = select(func.count(IncomingMessage.id))
    if effective_tenant_id:
        inbound_q = inbound_q.where(IncomingMessage.tenant_id == effective_tenant_id)
    incoming_msgs = db.scalar(inbound_q) or 0

    # Devices
    dev_q = select(func.count(GatewayDevice.id)).where(GatewayDevice.is_revoked == False)
    if effective_tenant_id:
        dev_q = dev_q.where(or_(GatewayDevice.tenant_id == effective_tenant_id, GatewayDevice.is_shared_pool == True))
    total_devices = db.scalar(dev_q) or 0

    online_dev_q = select(func.count(GatewayDevice.id)).where(
        and_(GatewayDevice.is_online == True, GatewayDevice.is_revoked == False)
    )
    if effective_tenant_id:
        online_dev_q = online_dev_q.where(or_(GatewayDevice.tenant_id == effective_tenant_id, GatewayDevice.is_shared_pool == True))
    online_devices = db.scalar(online_dev_q) or 0
    offline_devices = max(0, total_devices - online_devices)

    # Webhooks
    total_webhooks = db.scalar(select(func.count(WebhookSubscription.id)).where(WebhookSubscription.is_active == True)) or 0
    delivered_webhooks = db.scalar(select(func.count(WebhookDelivery.id)).where(WebhookDelivery.status == "delivered")) or 0
    failed_webhooks = db.scalar(select(func.count(WebhookDelivery.id)).where(WebhookDelivery.status == "failed")) or 0

    # Tanzania MNO Breakdown
    mno_query = select(Message.detected_mno, func.count(Message.id))
    if msg_filter:
        mno_query = mno_query.where(*msg_filter)
    mno_rows = db.execute(mno_query.group_by(Message.detected_mno)).fetchall()
    mno_breakdown = {row[0] or "UNKNOWN": row[1] for row in mno_rows}

    # Timeseries (Last 12 hours)
    now = datetime.now(timezone.utc)
    timeseries_labels = []
    timeseries_sent = []
    timeseries_delivered = []
    timeseries_failed = []
    timeseries_received = []

    for i in range(11, -1, -1):
        slot_start = (now - timedelta(hours=i + 1)).replace(minute=0, second=0, microsecond=0)
        slot_end = slot_start + timedelta(hours=1)
        timeseries_labels.append(slot_start.strftime("%H:00"))

        def _count_slot(status_name: str) -> int:
            sq = select(func.count(Message.id)).where(
                and_(
                    Message.status == status_name,
                    Message.created_at >= slot_start,
                    Message.created_at < slot_end,
                )
            )
            if msg_filter:
                sq = sq.where(*msg_filter)
            return db.scalar(sq) or 0

        timeseries_sent.append(_count_slot("sent"))
        timeseries_delivered.append(_count_slot("delivered"))
        timeseries_failed.append(_count_slot("failed"))

        rx_q = select(func.count(IncomingMessage.id)).where(
            and_(
                IncomingMessage.received_at_device >= slot_start,
                IncomingMessage.received_at_device < slot_end,
            )
        )
        if effective_tenant_id:
            rx_q = rx_q.where(IncomingMessage.tenant_id == effective_tenant_id)
        timeseries_received.append(db.scalar(rx_q) or 0)

    # Recent Audit Log
    recent_logs = []
    audit_events = db.scalars(select(AuditEvent).order_by(desc(AuditEvent.created_at)).limit(10)).all()
    for ev in audit_events:
        recent_logs.append({
            "action": ev.action,
            "actor": ev.actor_id or "system",
            "time": ev.created_at.strftime("%H:%M:%S"),
            "details": ev.details or {},
        })

    return {
        "summary": {
            "total_messages": total_msgs,
            "queued": queued_msgs,
            "sending": sending_msgs,
            "sent": sent_msgs,
            "delivered": delivered_msgs,
            "failed": failed_msgs,
            "rejected": rejected_msgs,
            "pending_approval": pending_approval,
            "scheduled": scheduled_msgs,
            "devices": total_devices,
            "devices_online": online_devices,
            "devices_offline": offline_devices,
            "total_devices": total_devices,
            "incoming": incoming_msgs,
            "webhooks_active": total_webhooks,
            "webhooks_delivered": delivered_webhooks,
            "webhooks_failed": failed_webhooks,
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
                "labels": ["Delivered", "Sent", "Queued", "Failed", "Pending Approval"],
                "data": [delivered_msgs, sent_msgs, queued_msgs, failed_msgs, pending_approval],
            },
        },
        "mno_breakdown": mno_breakdown,
        "kill_switch": get_kill_switch_status(),
        "timeseries": {
            "labels": timeseries_labels,
            "sent": timeseries_sent,
            "delivered": timeseries_delivered,
            "failed": timeseries_failed,
            "received": timeseries_received,
        },
        "recent_activity": recent_logs,
        "system_info": {
            "os": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "server_time": now.isoformat(),
        },
    }


# -------------------------------------------------------------
# 2. Per-SMS Inline Modification & Batch Actions
# -------------------------------------------------------------
@router.patch("/messages/{message_id}/modify", response_model=MessageResponse)
def modify_single_message(
    message_id: str,
    payload: MessageModifyRequest,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Allows Super Admin or Tenant Admin to edit an unsent message before radio dispatch."""
    admin_id = admin.get("user_id") or admin.get("sub", "admin")
    try:
        return modify_message(db, message_id, payload, admin_id=admin_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Message '{message_id}' not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/messages/batch-action", response_model=BatchActionResponse)
def execute_batch_action(
    payload: BatchActionRequest,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Approve, reject (with refund), cancel, or force reroute quarantined/queued messages."""
    admin_id = admin.get("user_id") or admin.get("sub", "admin")
    return batch_action_messages(db, payload, admin_id=admin_id)


# -------------------------------------------------------------
# 3. Emergency Kill-Switch Endpoint
# -------------------------------------------------------------
@router.post("/system/kill-switch", response_model=KillSwitchResponse)
def toggle_system_kill_switch(
    payload: KillSwitchRequest,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    """Halts all outbound job leasing immediately without dropping incoming webhooks."""
    res = set_kill_switch(payload.enabled, tenant_id=payload.tenant_id)
    scope = f"tenant {payload.tenant_id}" if payload.tenant_id else "global system"
    state_str = "PAUSED" if payload.enabled else "RESUMED"
    return KillSwitchResponse(
        global_paused=res["global_paused"],
        paused_tenants=res["paused_tenants"],
        message=f"Outbound SMS leasing {state_str} for {scope}. {payload.reason or ''}",
    )


@router.get("/system/kill-switch", response_model=KillSwitchResponse)
def get_kill_switch(admin: Dict[str, Any] = Depends(get_current_admin)):
    res = get_kill_switch_status()
    return KillSwitchResponse(
        global_paused=res["global_paused"],
        paused_tenants=res["paused_tenants"],
        message="Kill switch state retrieved",
    )


# -------------------------------------------------------------
# 4. Multi-Tenant Organization Management (Super Admin)
# -------------------------------------------------------------
@router.get("/tenants", response_model=List[TenantResponse])
def list_tenants(
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Lists all tenants (Organizations)."""
    return db.scalars(select(Tenant).order_by(Tenant.created_at.desc())).all()


@router.post("/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Creates a new tenant organization."""
    existing = db.scalar(select(Tenant).where(Tenant.slug == payload.slug.strip().lower()))
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Tenant slug '{payload.slug}' already exists.")

    tenant = Tenant(
        name=payload.name.strip(),
        slug=payload.slug.strip().lower(),
        can_use_shared_devices=payload.can_use_shared_devices,
        require_bulk_approval_threshold=payload.require_bulk_approval_threshold,
        allowed_sender_names=payload.allowed_sender_names,
        daily_sms_limit=payload.daily_sms_limit,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
def get_tenant(
    tenant_id: str,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    t = db.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return t


# -------------------------------------------------------------
# 5. User Management Console
# -------------------------------------------------------------
@router.get("/users", response_model=List[UserResponse])
def list_users(
    tenant_id: Optional[str] = None,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Lists users, optionally filtered by tenant."""
    query = select(User)
    if tenant_id:
        query = query.where(User.tenant_id == tenant_id)
    return db.scalars(query.order_by(desc(User.created_at))).all()


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Creates a new user under a tenant organization."""
    existing = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Email '{payload.email}' already registered.")

    user = User(
        email=payload.email.strip().lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=payload.role,
        tenant_id=payload.tenant_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# -------------------------------------------------------------
# 6. Credit Ledger & Audit History
# -------------------------------------------------------------
@router.get("/credit-transactions")
def get_credit_ledger(
    tenant_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Retrieves immutable credit ledger records."""
    effective_tenant_id = admin.get("tenant_id") or tenant_id
    txs = list_credit_transactions(db, tenant_id=effective_tenant_id, limit=limit, offset=offset)
    return [
        {
            "id": tx.id,
            "tenant_id": tx.tenant_id,
            "bundle_id": tx.bundle_id,
            "message_id": tx.message_id,
            "tx_type": tx.tx_type,
            "amount": tx.amount,
            "balance_after": tx.balance_after,
            "reason": tx.reason,
            "created_at": tx.created_at.isoformat(),
        }
        for tx in txs
    ]


# -------------------------------------------------------------
# 7. TCRA DND Blacklist Management
# -------------------------------------------------------------
@router.get("/dnd", response_model=List[DndBlacklistResponse])
def list_dnd_blacklist(
    tenant_id: Optional[str] = None,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Lists DND opt-out records."""
    effective_tenant_id = admin.get("tenant_id") or tenant_id
    query = select(DndBlacklist)
    if effective_tenant_id:
        query = query.where(or_(DndBlacklist.tenant_id == effective_tenant_id, DndBlacklist.tenant_id == None))
    return db.scalars(query.order_by(desc(DndBlacklist.created_at))).all()


@router.post("/dnd", response_model=DndBlacklistResponse, status_code=status.HTTP_201_CREATED)
def add_dnd_blacklist(
    payload: DndBlacklistCreate,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Manually blocks a phone number from receiving promotional SMS."""
    from app.utils.phone_tz import normalize_tz_phone
    norm = normalize_tz_phone(payload.phone_number)
    entry = DndBlacklist(
        phone_number=norm,
        reason=payload.reason,
        tenant_id=payload.tenant_id or admin.get("tenant_id"),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/dnd/{dnd_id}")
def remove_dnd_blacklist(
    dnd_id: str,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    entry = db.get(DndBlacklist, dnd_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DND entry not found")
    db.delete(entry)
    db.commit()
    return {"status": "success", "message": "Phone number removed from DND blacklist"}


# -------------------------------------------------------------
# 8. Content Moderation Firewall Rules
# -------------------------------------------------------------
@router.get("/moderation-rules", response_model=List[ModerationRuleResponse])
def list_moderation_rules(
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Lists regex content moderation rules."""
    return db.scalars(select(ContentModerationRule).order_by(desc(ContentModerationRule.created_at))).all()


@router.post("/moderation-rules", response_model=ModerationRuleResponse, status_code=status.HTTP_201_CREATED)
def create_moderation_rule(
    payload: ModerationRuleCreate,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Creates a new regex content firewall rule."""
    rule = ContentModerationRule(
        name=payload.name.strip(),
        pattern=payload.pattern.strip(),
        action=payload.action,
        replacement_text=payload.replacement_text,
        is_active=payload.is_active,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/moderation-rules/{rule_id}")
def delete_moderation_rule(
    rule_id: str,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    rule = db.get(ContentModerationRule, rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return {"status": "success", "message": f"Rule '{rule.name}' deleted"}


# -------------------------------------------------------------
# 9. SMS Bundle & Top-up Management
# -------------------------------------------------------------
@router.get("/bundle")
def get_bundle_status(
    tenant_id: Optional[str] = None,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Retrieves current SMS bundle status and credit balance."""
    effective_tenant_id = admin.get("tenant_id") or tenant_id
    return get_bundle_summary(db, tenant_id=effective_tenant_id)


@router.post("/bundle/topup")
def topup_sms_bundle(
    payload: BundleTopupRequest,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Adds SMS credits to the active bundle and extends expiration."""
    effective_tenant_id = payload.tenant_id or admin.get("tenant_id")
    bundle = topup_bundle(
        db,
        credits_to_add=payload.credits,
        extend_days=payload.extend_days,
        plan_name=payload.plan_name,
        tenant_id=effective_tenant_id,
    )
    return get_bundle_summary(db, tenant_id=effective_tenant_id)


# -------------------------------------------------------------
# 10. API Key Management
# -------------------------------------------------------------
@router.get("/api-keys")
def list_api_keys(
    tenant_id: Optional[str] = None,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    effective_tenant_id = admin.get("tenant_id") or tenant_id
    query = select(ApiKey)
    if effective_tenant_id:
        query = query.where(ApiKey.tenant_id == effective_tenant_id)
    keys = db.scalars(query.order_by(desc(ApiKey.created_at))).all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "key_prefix": k.key_prefix,
            "scopes": k.scopes,
            "rate_limit": k.rate_limit,
            "allowed_ips": k.allowed_ips,
            "is_active": k.is_active,
            "created_at": k.created_at.isoformat(),
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
        }
        for k in keys
    ]


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
def create_api_key_admin(
    payload: ApiKeyCreateAdmin,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    raw_key, prefix, key_hash = generate_api_key(prefix="gw_")
    expires_at = None
    if payload.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)

    effective_tenant_id = payload.tenant_id or admin.get("tenant_id")

    api_key = ApiKey(
        tenant_id=effective_tenant_id,
        name=payload.name,
        key_hash=key_hash,
        key_prefix=prefix,
        scopes=payload.scopes,
        rate_limit=payload.rate_limit,
        allowed_ips=payload.allowed_ips,
        expires_at=expires_at,
        is_active=True,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return {
        "id": api_key.id,
        "name": api_key.name,
        "key_prefix": api_key.key_prefix,
        "raw_key": raw_key,
        "scopes": api_key.scopes,
        "rate_limit": api_key.rate_limit,
        "allowed_ips": api_key.allowed_ips,
        "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
    }


@router.delete("/api-keys/{key_id}")
def revoke_api_key(
    key_id: str,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    api_key = db.get(ApiKey, key_id)
    if not api_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    api_key.is_active = False
    db.commit()
    return {"status": "success", "message": f"API key '{api_key.name}' revoked."}


# -------------------------------------------------------------
# 11. Device Pairing Code Generation
# -------------------------------------------------------------
@router.post("/devices/generate-pairing-code")
@router.post("/devices/pairing-code")
def generate_pairing_code_for_phone(
    payload: PairingCodeAdminRequest,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    effective_tenant_id = payload.tenant_id or admin.get("tenant_id")
    pairing_code = create_pairing_code(
        db,
        device_name=payload.device_name,
        expires_in_seconds=payload.expires_in_seconds,
        tenant_id=effective_tenant_id,
    )
    return {
        "code": pairing_code.code,
        "device_name": pairing_code.device_name,
        "expires_at": pairing_code.expires_at.isoformat(),
        "expires_in_seconds": payload.expires_in_seconds,
    }


# -------------------------------------------------------------
# 12. Webhook Testing Dispatch
# -------------------------------------------------------------
@router.post("/webhooks/{subscription_id}/test")
def test_webhook_delivery(
    subscription_id: str,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    sub = db.get(WebhookSubscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook subscription not found")

    test_deliveries = queue_event(
        db,
        event_type="test.ping",
        data={
            "ping": "pong",
            "message": "Manual webhook test triggered from mission control",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        tenant_id=sub.tenant_id,
    )
    target_delivery = next((d for d in test_deliveries if d.subscription_id == sub.id), None)
    if not target_delivery:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not queue test delivery")

    result = deliver_webhook_sync(db, target_delivery)
    return {
        "delivery_id": result.id,
        "status": result.status,
        "response_code": result.response_status_code,
        "error": result.error_message,
    }


# -------------------------------------------------------------
# 13. Git Synchronization & cPanel Auto-Update
# -------------------------------------------------------------
@router.get("/system/git-status")
def get_system_git_status(
    force: bool = False,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    """Checks local commit against remote repository and returns update availability."""
    from app.services.git_sync_service import get_git_sync_status
    return get_git_sync_status(force_refresh=force)


@router.post("/system/git-sync")
def trigger_system_git_sync(
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    """
    Executes automated git pull/reset from GitHub, touches tmp/restart.txt,
    and reloads the cPanel Phusion Passenger server.
    """
    role = admin.get("role")
    if role not in ("super_admin", "superadmin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin privileges required to update and restart the server.",
        )
    from app.services.git_sync_service import perform_git_sync
    result = perform_git_sync()
    if not result.get("success"):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.get("error"))
    return result


# -------------------------------------------------------------
# 14. Google AI Studio (Gemini) Intelligence Configuration
# -------------------------------------------------------------
class AiConfigResponse(BaseModel):
    ai_auto_reply_enabled: bool
    gemini_api_key_set: bool
    gemini_api_key_masked: str
    gemini_model: str
    ai_system_prompt: str
    ai_max_output_tokens: int
    ai_temperature: float
    ai_reply_sender_name: str
    env_file_path: str


class AiConfigUpdateRequest(BaseModel):
    ai_auto_reply_enabled: bool
    gemini_api_key: Optional[str] = None
    gemini_model: str = Field("gemini-1.5-flash", min_length=1)
    ai_system_prompt: str = Field(..., min_length=1)
    ai_max_output_tokens: int = Field(150, ge=30, le=1000)
    ai_temperature: float = Field(0.7, ge=0.0, le=1.0)
    ai_reply_sender_name: Optional[str] = None


class AiPlaygroundTestRequest(BaseModel):
    message: str = Field(..., min_length=1)
    system_instruction: Optional[str] = None
    model: Optional[str] = None


class AiPlaygroundTestResponse(BaseModel):
    status: str
    reply: Optional[str] = None
    model: str
    latency_ms: int = 0
    characters: int = 0
    sms_parts: int = 0
    error: Optional[str] = None


@router.get("/ai-config", response_model=AiConfigResponse)
def get_ai_configuration(
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    """Returns the active AI configuration with API key safely masked."""
    from app.services.ai_service import find_env_file_path

    key = settings.GEMINI_API_KEY or ""
    masked = ""
    if key and len(key) > 8:
        masked = f"{key[:6]}...{key[-4:]}"
    elif key:
        masked = "••••••••"

    return AiConfigResponse(
        ai_auto_reply_enabled=settings.AI_AUTO_REPLY_ENABLED,
        gemini_api_key_set=bool(key.strip()),
        gemini_api_key_masked=masked,
        gemini_model=settings.GEMINI_MODEL,
        ai_system_prompt=settings.AI_SYSTEM_PROMPT,
        ai_max_output_tokens=settings.AI_MAX_OUTPUT_TOKENS,
        ai_temperature=settings.AI_TEMPERATURE,
        ai_reply_sender_name=settings.AI_REPLY_SENDER_NAME or "",
        env_file_path=find_env_file_path(),
    )


@router.post("/ai-config", response_model=AiConfigResponse)
def update_ai_configuration(
    payload: AiConfigUpdateRequest,
    admin: Dict[str, Any] = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Updates the runtime AI configuration and writes the changes directly into the server's .env file.
    """
    from app.services.ai_service import persist_ai_config_to_env, find_env_file_path

    env_updates: Dict[str, Any] = {
        "AI_AUTO_REPLY_ENABLED": payload.ai_auto_reply_enabled,
        "GEMINI_MODEL": payload.gemini_model.strip(),
        "AI_SYSTEM_PROMPT": payload.ai_system_prompt.strip(),
        "AI_MAX_OUTPUT_TOKENS": payload.ai_max_output_tokens,
        "AI_TEMPERATURE": payload.ai_temperature,
        "AI_REPLY_SENDER_NAME": (payload.ai_reply_sender_name or "").strip(),
    }

    # Only update the API key if explicitly passed (not empty)
    if payload.gemini_api_key is not None and payload.gemini_api_key.strip():
        env_updates["GEMINI_API_KEY"] = payload.gemini_api_key.strip()

    env_path = persist_ai_config_to_env(env_updates)

    record_audit_event(
        db,
        action="ai.config_updated",
        actor_type="admin",
        actor_id=admin.get("sub", "admin"),
        details={
            "enabled": payload.ai_auto_reply_enabled,
            "model": payload.gemini_model,
            "key_updated": bool(payload.gemini_api_key and payload.gemini_api_key.strip()),
            "env_path": env_path,
        },
    )

    key = settings.GEMINI_API_KEY or ""
    masked = ""
    if key and len(key) > 8:
        masked = f"{key[:6]}...{key[-4:]}"
    elif key:
        masked = "••••••••"

    return AiConfigResponse(
        ai_auto_reply_enabled=settings.AI_AUTO_REPLY_ENABLED,
        gemini_api_key_set=bool(key.strip()),
        gemini_api_key_masked=masked,
        gemini_model=settings.GEMINI_MODEL,
        ai_system_prompt=settings.AI_SYSTEM_PROMPT,
        ai_max_output_tokens=settings.AI_MAX_OUTPUT_TOKENS,
        ai_temperature=settings.AI_TEMPERATURE,
        ai_reply_sender_name=settings.AI_REPLY_SENDER_NAME or "",
        env_file_path=env_path,
    )


@router.post("/ai-test", response_model=AiPlaygroundTestResponse)
def test_ai_playground_prompt(
    payload: AiPlaygroundTestRequest,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    """
    Executes a real-time prompt generation via Gemini, measuring latency and SMS part counts.
    """
    from app.services.ai_service import generate_gemini_reply
    from app.services.message_service import calculate_sms_parts

    if not settings.GEMINI_API_KEY or not settings.GEMINI_API_KEY.strip():
        return AiPlaygroundTestResponse(
            status="unconfigured",
            reply=None,
            model=payload.model or settings.GEMINI_MODEL,
            latency_ms=0,
            characters=0,
            sms_parts=0,
            error="GEMINI_API_KEY is not configured. Please paste your Google AI Studio API key in the configuration panel above and click Save.",
        )

    start_time = time.time()
    chosen_model = payload.model or settings.GEMINI_MODEL
    sys_prompt = payload.system_instruction or settings.AI_SYSTEM_PROMPT

    reply = generate_gemini_reply(
        prompt=payload.message,
        system_instruction=sys_prompt,
        model_override=chosen_model,
    )
    elapsed_ms = int((time.time() - start_time) * 1000)

    if not reply:
        return AiPlaygroundTestResponse(
            status="error",
            reply=None,
            model=chosen_model,
            latency_ms=elapsed_ms,
            characters=0,
            sms_parts=0,
            error="Failed to generate AI response. Please check your GEMINI_API_KEY or network connection.",
        )

    parts = calculate_sms_parts(reply)

    return AiPlaygroundTestResponse(
        status="success",
        reply=reply,
        model=chosen_model,
        latency_ms=elapsed_ms,
        characters=len(reply),
        sms_parts=parts,
    )

