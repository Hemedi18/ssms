import math
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, and_

from app.core.config import settings
from app.core.logging import logger
from app.core.security import normalize_and_validate_phone
from app.models.message import Message, MessageEvent
from app.schemas.message import MessageCreate, MessageFilterParams
from app.services.webhook_service import queue_event
from app.services.audit_service import record_audit_event


def calculate_sms_parts(body: str) -> int:
    """Calculates SMS part count based on GSM 03.38 standard (160 / 153 chars)."""
    length = len(body)
    if length <= 160:
        return 1
    return math.ceil(length / 153)


def create_message(
    db: Session,
    payload: MessageCreate,
    actor_id: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> Tuple[Message, bool]:
    """
    Creates an outgoing SMS job in 'queued' state.
    Returns (message, is_duplicate).
    """
    # 1. Idempotency check
    if payload.idempotency_key:
        existing = db.scalar(
            select(Message).where(Message.idempotency_key == payload.idempotency_key)
        )
        if existing:
            logger.info(f"Idempotent message hit: returning existing message {existing.id}")
            return existing, True

    # 2. Normalize and validate E.164
    normalized_to = normalize_and_validate_phone(
        payload.to, default_country_code=settings.DEFAULT_COUNTRY_CODE
    )

    # 3. Recipient allowlist check (for development / testing environments)
    if settings.RECIPIENT_ALLOWLIST:
        if normalized_to not in settings.RECIPIENT_ALLOWLIST:
            raise ValueError(
                f"Destination {normalized_to} is not permitted by RECIPIENT_ALLOWLIST policy."
            )

    # 4. Message content validation
    body = (payload.body or payload.message or "").strip()
    if not body:
        raise ValueError("Message body cannot be empty")
    if len(body) > settings.MAX_MESSAGE_LENGTH:
        raise ValueError(
            f"Message length ({len(body)}) exceeds maximum limit of {settings.MAX_MESSAGE_LENGTH} characters."
        )

    parts_count = calculate_sms_parts(body)

    # 5. Persist Message
    message = Message(
        to=normalized_to,
        body=body,
        status="queued",
        client_reference=payload.client_reference,
        idempotency_key=payload.idempotency_key,
        parts_count=parts_count,
    )
    db.add(message)
    db.flush()

    # 6. Add initial queued event
    event = MessageEvent(
        message_id=message.id,
        status="queued",
        error_details="Job queued for gateway dispatch",
    )
    db.add(event)
    db.commit()
    db.refresh(message)

    # 7. Audit and Webhook
    record_audit_event(
        db,
        action="message.create",
        actor_type="api_key",
        actor_id=actor_id,
        details={"message_id": message.id, "to": normalized_to, "parts": parts_count},
        ip_address=ip_address,
    )

    queue_event(
        db,
        event_type="sms.queued",
        data={
            "message_id": message.id,
            "to": message.to,
            "status": "queued",
            "parts_count": parts_count,
            "client_reference": message.client_reference,
            "created_at": message.created_at.isoformat(),
        },
    )

    return message, False


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

    if message.status not in ("failed", "unknown"):
        raise ValueError(
            f"Only messages in 'failed' or 'unknown' state can be retried. Current status is '{message.status}'."
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

    record_audit_event(
        db,
        action="message.retry",
        actor_type="api_key",
        actor_id=actor_id,
        details={"message_id": message.id},
        ip_address=ip_address,
    )

    queue_event(
        db,
        event_type="sms.queued",
        data={
            "message_id": message.id,
            "to": message.to,
            "status": "queued",
            "retried": True,
        },
    )

    return message


def list_messages(
    db: Session, params: MessageFilterParams
) -> Tuple[List[Message], int]:
    """Lists messages with optional filters and total count."""
    filters = []
    if params.status:
        filters.append(Message.status == params.status)
    if params.to:
        filters.append(Message.to.contains(params.to))

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
