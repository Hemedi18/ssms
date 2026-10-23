from sqlalchemy.orm import Session
from app.models.audit import AuditEvent
from app.core.logging import logger, sanitize_log_dict
from typing import Optional, Dict, Any


def record_audit_event(
    db: Session,
    action: str,
    actor_type: str,
    actor_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> AuditEvent:
    clean_details = sanitize_log_dict(details or {})
    event = AuditEvent(
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        details=clean_details,
        ip_address=ip_address,
    )
    db.add(event)
    db.commit()
    logger.info(f"Audit [{action}] by [{actor_type}:{actor_id or 'none'}]")
    return event
