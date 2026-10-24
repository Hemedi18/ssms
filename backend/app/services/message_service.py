import math
import re
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Set, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, and_, or_

from app.core.config import settings
from app.core.logging import logger
from app.core.security import normalize_and_validate_phone
from app.models.message import Message, MessageEvent
from app.models.dnd_and_moderation import DndBlacklist, ContentModerationRule
from app.models.tenant import Tenant
from app.schemas.message import (
    MessageCreate,
    MessageFilterParams,
    BulkMessageCreate,
    BulkMessageResponse,
    MessageModifyRequest,
    BatchActionRequest,
    BatchActionResponse,
)
from app.services.webhook_service import queue_event
from app.services.audit_service import record_audit_event
from app.services.bundle_service import (
    check_and_deduct_credits,
    refund_credits,
    get_or_create_active_bundle,
)
from app.utils.phone_tz import (
    normalize_tz_phone,
    classify_mno,
    calculate_sms_encoding_and_parts,
    is_tcra_quiet_hours,
    render_spintax,
    interpolate_variables,
)


def calculate_sms_parts(body: str) -> int:
    """Calculates SMS part count using exact GSM 03.38 / UCS-2 standard."""
    _, parts, _ = calculate_sms_encoding_and_parts(body)
    return parts


def format_message_with_brand(body: str, sender_name: Optional[str]) -> str:
    """
    Prepends sender brand identifier to SMS body if not already present.
    Example: "[EDUSPHERE] Your OTP code is 4921"
    """
    clean_body = body.strip()
    if not sender_name:
        return clean_body

    brand = sender_name.strip()
    if not brand:
        return clean_body

    prefix_bracket = f"[{brand}]"
    prefix_colon = f"{brand}:"
    if clean_body.startswith(prefix_bracket) or clean_body.startswith(prefix_colon):
        return clean_body

    return f"[{brand}] {clean_body}"


def _apply_content_moderation(
    db: Session, text: str
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Applies active ContentModerationRule rules.
    Returns: (final_body, original_body_if_replaced, forced_status_or_none)
    Raises: ValueError if rule action is 'reject'.
    """
    rules = db.scalars(
        select(ContentModerationRule).where(ContentModerationRule.is_active == True)
    ).all()

    current_body = text
    orig_body: Optional[str] = None
    forced_status: Optional[str] = None

    for rule in rules:
        try:
            pattern = re.compile(rule.pattern, re.IGNORECASE)
            if pattern.search(current_body):
                if rule.action == "reject":
                    raise ValueError(f"Message blocked by content moderation firewall (Rule: {rule.name})")
                elif rule.action == "hold_for_approval":
                    forced_status = "pending_approval"
                elif rule.action == "auto_replace":
                    if orig_body is None:
                        orig_body = current_body
                    current_body = pattern.sub(rule.replacement_text or "", current_body)
        except re.error:
            continue

    return current_body, orig_body, forced_status


# ---------------------------------------------------------------------------
# Create Outgoing SMS
# ---------------------------------------------------------------------------
def create_message(
    db: Session,
    payload: MessageCreate,
    actor_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> Tuple[Message, bool]:
    """
    Creates an outgoing SMS job in 'queued', 'scheduled', or 'pending_approval' state.
    Validates E.164, classifies MNO, applies GSM/UCS-2 encoding, checks DND and moderation.
    Returns (message, is_duplicate).
    """
    effective_tenant_id = payload.tenant_id or tenant_id

    # 1. Idempotency check
    if payload.idempotency_key:
        existing = db.scalar(
            select(Message).where(Message.idempotency_key == payload.idempotency_key)
        )
        if existing:
            logger.info(f"Idempotent message hit: returning existing message {existing.id}")
            return existing, True

    # 2. Normalize and classify phone
    normalized_to = normalize_tz_phone(
        payload.to, default_country_code=settings.DEFAULT_COUNTRY_CODE
    )
    detected_mno = classify_mno(normalized_to)

    # 3. Recipient allowlist check (if configured in dev)
    if settings.RECIPIENT_ALLOWLIST and normalized_to not in settings.RECIPIENT_ALLOWLIST:
        raise ValueError(f"Destination {normalized_to} is not permitted by RECIPIENT_ALLOWLIST policy.")

    # 4. TCRA DND Blacklist check for promotional SMS
    is_promo = payload.message_type.lower() == "promotional"
    if is_promo:
        dnd_entry = db.scalar(
            select(DndBlacklist).where(
                and_(
                    DndBlacklist.phone_number == normalized_to,
                    or_(
                        DndBlacklist.tenant_id == effective_tenant_id,
                        DndBlacklist.tenant_id == None,
                    ),
                )
            )
        )
        if dnd_entry:
            raise ValueError(
                f"Destination {normalized_to} is on the DND Opt-Out Blacklist (Reason: {dnd_entry.reason}). Cannot send promotional message."
            )

    # 5. Content moderation & formatting
    raw_body = (payload.body or payload.message or "").strip()
    if not raw_body:
        raise ValueError("Message body cannot be empty")

    formatted_body = format_message_with_brand(raw_body, payload.sender_name)
    if len(formatted_body) > settings.MAX_MESSAGE_LENGTH:
        raise ValueError(
            f"Message length ({len(formatted_body)}) exceeds maximum limit of {settings.MAX_MESSAGE_LENGTH} characters."
        )

    moderated_body, original_body, mod_status = _apply_content_moderation(db, formatted_body)

    # 6. GSM 03.38 vs UCS-2 Encoding & Part Count
    encoding, parts_count, _ = calculate_sms_encoding_and_parts(moderated_body)

    # 7. Check and deduct credits from active SMS Bundle
    check_and_deduct_credits(
        db,
        credits_needed=parts_count,
        tenant_id=effective_tenant_id,
        reason=f"SMS to {normalized_to} ({parts_count} parts)",
    )

    # 8. TCRA Quiet Hours check for promotional SMS
    initial_status = mod_status or "queued"
    scheduled_for_dt = None

    if is_promo and initial_status != "pending_approval":
        is_quiet, next_dispatch_utc = is_tcra_quiet_hours()
        if is_quiet:
            initial_status = "scheduled"
            scheduled_for_dt = next_dispatch_utc

    # 9. Persist Message
    message = Message(
        tenant_id=effective_tenant_id,
        to=normalized_to,
        body=moderated_body,
        original_body=original_body,
        status=initial_status,
        message_type=payload.message_type.lower(),
        priority=payload.priority,
        encoding=encoding,
        detected_mno=detected_mno,
        sender_name=payload.sender_name.strip() if payload.sender_name else None,
        sim_slot=payload.sim_slot,
        client_reference=payload.client_reference,
        idempotency_key=payload.idempotency_key,
        parts_count=parts_count,
        scheduled_for=scheduled_for_dt,
    )
    db.add(message)
    db.flush()

    # 10. Record Event
    event = MessageEvent(
        message_id=message.id,
        status=initial_status,
        error_details=(
            f"Job {initial_status} for gateway dispatch (MNO: {detected_mno}, Encoding: {encoding}, Priority: {payload.priority})"
        ),
    )
    db.add(event)
    db.commit()
    db.refresh(message)

    # 11. Audit and Webhook
    record_audit_event(
        db,
        action="message.create",
        actor_type="api_key",
        actor_id=actor_id,
        details={
            "message_id": message.id,
            "tenant_id": effective_tenant_id,
            "to": normalized_to,
            "parts": parts_count,
            "mno": detected_mno,
            "encoding": encoding,
            "status": initial_status,
        },
        ip_address=ip_address,
    )

    queue_event(
        db,
        event_type="sms.queued",
        data={
            "message_id": message.id,
            "tenant_id": effective_tenant_id,
            "to": message.to,
            "status": message.status,
            "parts_count": parts_count,
            "detected_mno": detected_mno,
            "encoding": encoding,
            "sender_name": message.sender_name,
            "sim_slot": message.sim_slot,
            "client_reference": message.client_reference,
            "created_at": message.created_at.isoformat(),
        },
    )

    return message, False


# ---------------------------------------------------------------------------
# Create Bulk Messages
# ---------------------------------------------------------------------------
def create_bulk_messages(
    db: Session,
    payload: BulkMessageCreate,
    actor_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> BulkMessageResponse:
    """
    Submits a batch of SMS messages with automated deduplication, normalization,
    MNO breakdown, Spintax rendering, variable interpolation, anti-spam pacing, and approval quarantine.
    """
    effective_tenant_id = payload.tenant_id or tenant_id
    raw_body = (payload.body or payload.message or "").strip()
    if not raw_body:
        raise ValueError("Message body cannot be empty")

    is_promo = payload.message_type.lower() == "promotional"

    # 1. Normalize and deduplicate recipients
    raw_list = payload.recipients
    total_raw = len(raw_list)

    seen: Set[str] = set()
    valid_recipients: List[str] = []
    invalid_count = 0
    duplicate_count = 0
    mno_counts: Dict[str, int] = {}

    # Pre-fetch DND numbers if promotional
    dnd_set = set()
    if is_promo:
        dnd_numbers = db.scalars(
            select(DndBlacklist.phone_number).where(
                or_(
                    DndBlacklist.tenant_id == effective_tenant_id,
                    DndBlacklist.tenant_id == None,
                )
            )
        ).all()
        dnd_set = set(dnd_numbers)

    for raw_phone in raw_list:
        clean = str(raw_phone).strip()
        if not clean:
            continue
        try:
            norm = normalize_tz_phone(clean, default_country_code=settings.DEFAULT_COUNTRY_CODE)
            if is_promo and norm in dnd_set:
                invalid_count += 1
                continue
            if norm in seen:
                duplicate_count += 1
            else:
                seen.add(norm)
                valid_recipients.append(norm)
                mno = classify_mno(norm)
                mno_counts[mno] = mno_counts.get(mno, 0) + 1
        except Exception:
            invalid_count += 1

    if not valid_recipients:
        raise ValueError("No valid recipient phone numbers found (or all opted-out via DND).")

    # 2. Check tenant approval threshold
    approval_threshold = 200
    if effective_tenant_id:
        tenant_obj = db.get(Tenant, effective_tenant_id)
        if tenant_obj:
            approval_threshold = tenant_obj.require_bulk_approval_threshold

    force_quarantine = len(valid_recipients) > approval_threshold

    # 3. Process first recipient to calculate base parts for deduction
    sample_text = format_message_with_brand(raw_body, payload.sender_name)
    _, base_parts, _ = calculate_sms_encoding_and_parts(sample_text)

    total_credits_needed = len(valid_recipients) * base_parts
    bundle = check_and_deduct_credits(
        db,
        credits_needed=total_credits_needed,
        tenant_id=effective_tenant_id,
        reason=f"Bulk SMS batch ({len(valid_recipients)} recipients, ~{total_credits_needed} credits)",
    )

    # 4. TCRA Quiet Hours check
    is_quiet, next_dispatch_utc = False, None
    if is_promo:
        is_quiet, next_dispatch_utc = is_tcra_quiet_hours()

    # 5. Create queued/pending messages
    created_message_ids: List[str] = []
    sender_name = payload.sender_name.strip() if payload.sender_name else None
    quarantined_count = 0

    for phone in valid_recipients:
        # Variable interpolation
        recipient_body = raw_body
        if payload.variables and phone in payload.variables:
            recipient_body = interpolate_variables(recipient_body, payload.variables[phone])

        # Spintax rendering
        if payload.use_spintax:
            recipient_body = render_spintax(recipient_body, seed=phone)

        branded_body = format_message_with_brand(recipient_body, sender_name)
        mod_body, orig_body, mod_status = _apply_content_moderation(db, branded_body)
        encoding, parts, _ = calculate_sms_encoding_and_parts(mod_body)
        mno = classify_mno(phone)

        if force_quarantine or mod_status == "pending_approval":
            msg_status = "pending_approval"
            quarantined_count += 1
            sched_dt = None
        elif is_quiet:
            msg_status = "scheduled"
            sched_dt = next_dispatch_utc
        else:
            msg_status = "queued"
            sched_dt = None

        msg = Message(
            tenant_id=effective_tenant_id,
            to=phone,
            body=mod_body,
            original_body=orig_body,
            status=msg_status,
            message_type=payload.message_type.lower(),
            priority=payload.priority,
            encoding=encoding,
            detected_mno=mno,
            sender_name=sender_name,
            sim_slot=payload.sim_slot,
            parts_count=parts,
            scheduled_for=sched_dt,
        )
        db.add(msg)
        db.flush()

        event = MessageEvent(
            message_id=msg.id,
            status=msg_status,
            error_details=f"Bulk SMS queued (Anti-Spam throttle: {payload.anti_spam_delay}s, Status: {msg_status})",
        )
        db.add(event)
        created_message_ids.append(msg.id)

    db.commit()

    estimated_seconds = len(valid_recipients) * payload.anti_spam_delay
    estimated_time_minutes = round(estimated_seconds / 60, 1)

    return BulkMessageResponse(
        total_recipients=total_raw,
        valid_recipients=len(valid_recipients),
        duplicates_removed=duplicate_count,
        invalid_recipients=invalid_count,
        queued_messages=len(created_message_ids),
        credits_deducted=total_credits_needed,
        remaining_credits=bundle.available_credits,
        estimated_time_minutes=estimated_time_minutes,
        message_ids=created_message_ids,
        quarantined_count=quarantined_count,
        mno_breakdown=mno_counts,
        message=(
            f"Successfully processed {len(created_message_ids)} messages. "
            f"({quarantined_count} quarantined for approval, {len(created_message_ids) - quarantined_count} queued/scheduled). "
            f"Anti-spam carrier protection enabled with {payload.anti_spam_delay}s intervals."
        ),
    )


# ---------------------------------------------------------------------------
# Per-SMS Inline Modification (Admin / Quarantine Control)
# ---------------------------------------------------------------------------
def modify_message(
    db: Session,
    message_id: str,
    payload: MessageModifyRequest,
    admin_id: Optional[str] = None,
) -> Message:
    """
    Allows modification of an unsent message (pending_approval, scheduled, queued).
    Preserves original_body, recalculates parts and encoding, adjusts credits automatically.
    """
    message = db.get(Message, message_id)
    if not message:
        raise KeyError(f"Message {message_id} not found")

    if message.status not in ("pending_approval", "scheduled", "queued"):
        raise ValueError(f"Cannot modify message in '{message.status}' status. Only pending or queued messages can be modified.")

    # Preserve original body if not already saved
    if message.original_body is None:
        message.original_body = message.body

    old_parts = message.parts_count

    if payload.to:
        message.to = normalize_tz_phone(payload.to)
        message.detected_mno = classify_mno(message.to)

    if payload.sender_name is not None:
        message.sender_name = payload.sender_name.strip() if payload.sender_name else None

    if payload.sim_slot is not None:
        message.sim_slot = payload.sim_slot

    if payload.priority is not None:
        message.priority = payload.priority

    if payload.admin_notes is not None:
        message.admin_notes = payload.admin_notes

    if payload.body:
        branded_body = format_message_with_brand(payload.body, message.sender_name)
        encoding, new_parts, _ = calculate_sms_encoding_and_parts(branded_body)
        message.body = branded_body
        message.encoding = encoding
        message.parts_count = new_parts

        # Credit difference reconciliation
        credit_delta = new_parts - old_parts
        if credit_delta > 0:
            check_and_deduct_credits(
                db,
                credits_needed=credit_delta,
                tenant_id=message.tenant_id,
                message_id=message.id,
                reason=f"Admin modification added +{credit_delta} parts",
            )
        elif credit_delta < 0:
            refund_credits(
                db,
                credits_to_refund=abs(credit_delta),
                tenant_id=message.tenant_id,
                message_id=message.id,
                reason=f"Admin modification reduced {abs(credit_delta)} parts",
            )

    message.modified_by_admin_id = admin_id
    message.updated_at = datetime.now(timezone.utc)

    event = MessageEvent(
        message_id=message.id,
        status="modified",
        error_details=f"Modified by Admin [{admin_id}]. Notes: {payload.admin_notes or 'None'}",
    )
    db.add(event)
    db.commit()
    db.refresh(message)

    logger.info(f"Message [{message.id}] successfully modified by admin [{admin_id}]")
    return message


# ---------------------------------------------------------------------------
# Batch Actions (Approve, Reject, Cancel, Reroute)
# ---------------------------------------------------------------------------
def batch_action_messages(
    db: Session,
    req: BatchActionRequest,
    admin_id: Optional[str] = None,
) -> BatchActionResponse:
    """
    Executes bulk actions across quarantined or queued messages.
    - 'approve': releases messages from 'pending_approval' to 'queued'.
    - 'reject' / 'cancel': marks 'rejected'/'cancelled' and refunds all consumed credits.
    - 'force_reroute': changes device or SIM slot assignment.
    """
    messages = db.scalars(
        select(Message).where(Message.id.in_(req.message_ids))
    ).all()

    affected_count = 0
    total_refunded = 0
    action = req.action.lower()

    for msg in messages:
        if action == "approve":
            if msg.status == "pending_approval":
                msg.status = "queued"
                event = MessageEvent(
                    message_id=msg.id,
                    status="queued",
                    error_details=f"Approved by Admin [{admin_id}]",
                )
                db.add(event)
                affected_count += 1

        elif action in ("reject", "cancel"):
            if msg.status in ("pending_approval", "scheduled", "queued", "dispatched"):
                target_st = "rejected" if action == "reject" else "cancelled"
                msg.status = target_st
                msg.error_message = req.admin_notes or f"Message {target_st} by Admin"
                # Refund credits
                refund_credits(
                    db,
                    credits_to_refund=msg.parts_count,
                    tenant_id=msg.tenant_id,
                    message_id=msg.id,
                    reason=f"Admin batch {action}: {req.admin_notes or 'No reason provided'}",
                )
                total_refunded += msg.parts_count
                event = MessageEvent(
                    message_id=msg.id,
                    status=target_st,
                    error_details=f"Batch {action} by Admin [{admin_id}]. Refunded {msg.parts_count} credits.",
                )
                db.add(event)
                affected_count += 1

        elif action == "force_reroute":
            if req.target_sim_slot is not None:
                msg.sim_slot = req.target_sim_slot
            if req.target_device_id is not None:
                msg.device_id = req.target_device_id
            if req.new_sender_name:
                msg.sender_name = req.new_sender_name.strip()
            affected_count += 1

    db.commit()

    return BatchActionResponse(
        action=action,
        affected_count=affected_count,
        credits_refunded=total_refunded,
        message=f"Batch action '{action}' completed for {affected_count} messages. {total_refunded} credits refunded.",
    )


# ---------------------------------------------------------------------------
# Retry Message & List Messages
# ---------------------------------------------------------------------------
def retry_message(
    db: Session,
    message_id: str,
    actor_id: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> Message:
    """Retries a failed message by setting status back to 'queued'."""
    message = db.get(Message, message_id)
    if not message:
        raise KeyError(f"Message {message_id} not found")

    if message.status not in ("failed", "unknown", "rejected", "cancelled"):
        raise ValueError(
            f"Only messages in 'failed', 'rejected', or 'cancelled' state can be retried. Current status is '{message.status}'."
        )

    # Re-deduct credits if it was previously refunded
    check_and_deduct_credits(
        db,
        credits_needed=message.parts_count,
        tenant_id=message.tenant_id,
        message_id=message.id,
        reason=f"Retry re-deduction for message {message.id}",
    )

    message.status = "queued"
    message.error_message = None
    message.lease_token = None
    message.leased_at = None
    message.lease_expires_at = None

    event = MessageEvent(
        message_id=message.id,
        status="queued",
        error_details="Manual retry triggered",
    )
    db.add(event)
    db.commit()
    db.refresh(message)

    queue_event(
        db,
        event_type="sms.queued",
        data={
            "message_id": message.id,
            "tenant_id": message.tenant_id,
            "to": message.to,
            "status": "queued",
            "retried": True,
        },
    )

    return message


def list_messages(
    db: Session, params: MessageFilterParams
) -> Tuple[List[Message], int]:
    """Lists messages with optional tenant, status, MNO, and search filters."""
    filters = []
    if params.status:
        filters.append(Message.status == params.status)
    if params.to:
        filters.append(Message.to.contains(params.to))
    if params.tenant_id:
        filters.append(Message.tenant_id == params.tenant_id)
    if params.message_type:
        filters.append(Message.message_type == params.message_type)
    if params.detected_mno:
        filters.append(Message.detected_mno == params.detected_mno)

    query = select(Message)
    if filters:
        query = query.where(and_(*filters))

    total = len(db.scalars(query).all())
    messages = db.scalars(
        query.order_by(desc(Message.created_at))
        .offset(params.offset)
        .limit(params.limit)
    ).all()

    return messages, total
