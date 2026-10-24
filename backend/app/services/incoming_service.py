import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, and_

from app.core.logging import logger
from app.models.incoming_message import IncomingMessage
from app.models.device import GatewayDevice
from app.models.dnd_and_moderation import DndBlacklist
from app.schemas.incoming import IncomingSmsReportRequest
from app.services.webhook_service import queue_event
from app.utils.phone_tz import is_opt_out_keyword, normalize_tz_phone


def compute_pdu_hash(from_number: str, body: str, received_at: datetime) -> str:
    raw = f"{from_number}:{body}:{received_at.isoformat()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ingest_incoming_sms(
    db: Session,
    device: GatewayDevice,
    req: IncomingSmsReportRequest,
) -> Tuple[IncomingMessage, bool]:
    """
    Ingests and deduplicates incoming SMS received on Android handset.
    Detects TCRA opt-out keywords (STOP, ONDOA, JIONDOE) and registers DND blacklisting.
    Returns (incoming_message, is_duplicate).
    """
    pdu_hash = req.pdu_hash or compute_pdu_hash(
        req.from_number, req.body, req.received_at
    )

    # Deduplication check
    existing = db.scalar(
        select(IncomingMessage).where(
            and_(
                IncomingMessage.from_number == req.from_number,
                IncomingMessage.raw_pdu_hash == pdu_hash,
            )
        )
    )
    if existing:
        logger.info(f"Duplicate incoming SMS ignored for message {existing.id}")
        return existing, True

    incoming = IncomingMessage(
        tenant_id=device.tenant_id,
        device_message_id=req.device_message_id,
        from_number=req.from_number,
        body=req.body,
        received_at_device=req.received_at,
        is_multipart=req.is_multipart,
        part_index=req.part_index,
        total_parts=req.total_parts,
        raw_pdu_hash=pdu_hash,
        device_id=device.id,
        synced_at=datetime.now(timezone.utc),
    )
    db.add(incoming)
    db.commit()
    db.refresh(incoming)

    logger.info(
        f"Incoming SMS ingested from {req.from_number} on device [{device.id}], id={incoming.id}"
    )

    # TCRA DND Automated Opt-Out Check
    if is_opt_out_keyword(req.body):
        try:
            norm_phone = normalize_tz_phone(req.from_number)
            # Check if already blacklisted
            existing_dnd = db.scalar(
                select(DndBlacklist).where(
                    and_(
                        DndBlacklist.phone_number == norm_phone,
                        DndBlacklist.tenant_id == device.tenant_id,
                    )
                )
            )
            if not existing_dnd:
                dnd_entry = DndBlacklist(
                    tenant_id=device.tenant_id,
                    phone_number=norm_phone,
                    reason="user_opt_out",
                    source_incoming_id=incoming.id,
                )
                db.add(dnd_entry)
                db.commit()
                logger.info(f"Automatically added {norm_phone} to DND blacklist from opt-out text '{req.body}'")
        except Exception as e:
            logger.warning(f"Failed to record DND opt-out: {e}")

    # Emit sms.received webhook
    queue_event(
        db,
        event_type="sms.received",
        data={
            "id": incoming.id,
            "tenant_id": incoming.tenant_id,
            "from": incoming.from_number,
            "body": incoming.body,
            "received_at": incoming.received_at_device.isoformat(),
            "device_id": device.id,
            "is_multipart": incoming.is_multipart,
        },
    )

    return incoming, False


def list_incoming_messages(
    db: Session,
    from_number: Optional[str] = None,
    tenant_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[IncomingMessage], int]:
    """Lists incoming SMS history with optional tenant filtering."""
    query = select(IncomingMessage)
    if from_number:
        query = query.where(IncomingMessage.from_number.contains(from_number))
    if tenant_id:
        query = query.where(IncomingMessage.tenant_id == tenant_id)

    total = len(db.scalars(query).all())
    results = db.scalars(
        query.order_by(desc(IncomingMessage.received_at_device))
        .offset(offset)
        .limit(limit)
    ).all()

    return results, total
