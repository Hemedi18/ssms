from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_device, require_scope
from app.models.api_key import ApiKey
from app.models.device import GatewayDevice
from app.schemas.incoming import (
    IncomingSmsReportRequest,
    IncomingMessageResponse,
)
from app.services.incoming_service import (
    ingest_incoming_sms,
    list_incoming_messages,
)

router = APIRouter(tags=["Incoming SMS"])


@router.post(
    "/devices/incoming",
    response_model=IncomingMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def report_incoming_sms(
    payload: IncomingSmsReportRequest,
    response: Response,
    device: GatewayDevice = Depends(get_current_device),
    db: Session = Depends(get_db),
):
    """
    Called by Android incoming SMS broadcast receiver / worker to synchronize
    a message received on the phone's physical SIM card with the backend.
    """
    try:
        incoming, is_duplicate = ingest_incoming_sms(db, device, payload)
        if is_duplicate:
            response.status_code = status.HTTP_200_OK
        return incoming
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/incoming", response_model=List[IncomingMessageResponse])
def get_incoming_messages(
    from_number: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    api_key: ApiKey = Depends(require_scope("incoming:read")),
    db: Session = Depends(get_db),
):
    """Lists received SMS messages with sender filtering and pagination."""
    messages, _ = list_incoming_messages(
        db, from_number=from_number, limit=limit, offset=offset
    )
    return messages
