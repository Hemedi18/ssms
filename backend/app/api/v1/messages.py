from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.deps import get_db, require_scope
from app.models.api_key import ApiKey
from app.models.message import Message, MessageEvent
from app.schemas.message import (
    MessageCreate,
    MessageResponse,
    MessageEventResponse,
    MessageFilterParams,
)
from app.services.message_service import (
    create_message,
    retry_message,
    list_messages,
)

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.post("", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def submit_message(
    payload: MessageCreate,
    request: Request,
    response: Response,
    api_key: ApiKey = Depends(require_scope("sms:send")),
    db: Session = Depends(get_db),
):
    """
    Submits an outgoing SMS request to the persistent queue.
    Returns HTTP 201 for newly queued messages, HTTP 200 for idempotent duplicates.
    """
    client_ip = request.client.host if request.client else None
    try:
        message, is_duplicate = create_message(
            db, payload, actor_id=api_key.id, ip_address=client_ip
        )
        if is_duplicate:
            response.status_code = status.HTTP_200_OK
        return message
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=List[MessageResponse])
def get_messages(
    status_filter: Optional[str] = None,
    to: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    api_key: ApiKey = Depends(require_scope("sms:read")),
    db: Session = Depends(get_db),
):
    """Lists messages with optional status and recipient filters."""
    params = MessageFilterParams(status=status_filter, to=to, limit=limit, offset=offset)
    messages, _ = list_messages(db, params)
    return messages


@router.get("/{message_id}", response_model=MessageResponse)
def get_message(
    message_id: str,
    api_key: ApiKey = Depends(require_scope("sms:read")),
    db: Session = Depends(get_db),
):
    """Inspects a specific message and current status."""
    message = db.get(Message, message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message '{message_id}' not found",
        )
    return message


@router.get("/{message_id}/events", response_model=List[MessageEventResponse])
def get_message_events(
    message_id: str,
    api_key: ApiKey = Depends(require_scope("sms:read")),
    db: Session = Depends(get_db),
):
    """Retrieves full audit event history for a message."""
    message = db.get(Message, message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message '{message_id}' not found",
        )
    events = db.scalars(
        select(MessageEvent)
        .where(MessageEvent.message_id == message_id)
        .order_by(MessageEvent.created_at)
    ).all()
    return events


@router.post("/{message_id}/retry", response_model=MessageResponse)
def retry_failed_message(
    message_id: str,
    request: Request,
    api_key: ApiKey = Depends(require_scope("sms:send")),
    db: Session = Depends(get_db),
):
    """Safely retries an eligible failed message."""
    client_ip = request.client.host if request.client else None
    try:
        return retry_message(db, message_id, actor_id=api_key.id, ip_address=client_ip)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message '{message_id}' not found",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
