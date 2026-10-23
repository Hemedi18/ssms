from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.config import settings
from app.models.message import Message
from app.models.device import GatewayDevice

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint validating database connectivity and queue metrics."""
    try:
        # Check database connectivity
        db.execute(select(1)).scalar()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    queued_count = db.scalar(
        select(func.count(Message.id)).where(Message.status == "queued")
    ) or 0

    active_devices_count = db.scalar(
        select(func.count(GatewayDevice.id)).where(
            GatewayDevice.is_online == True,
            GatewayDevice.is_revoked == False
        )
    ) or 0

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "database": db_status,
        "metrics": {
            "queued_messages": queued_count,
            "active_devices": active_devices_count,
        },
    }
