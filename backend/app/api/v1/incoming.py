from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_device, require_scope
from app.core.config import settings
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
from app.services.ai_service import (
    process_incoming_sms_with_ai,
    generate_gemini_reply,
)

router = APIRouter(tags=["Incoming SMS"])


class TestAiReplyRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Incoming SMS test content")
    from_number: Optional[str] = Field("+255712345678", description="Mock sender phone number")
    system_instruction: Optional[str] = Field(None, description="Optional custom system prompt")


class TestAiReplyResponse(BaseModel):
    status: str
    reply: Optional[str] = None
    model: str
    length: int = 0
    configured: bool
    note: Optional[str] = None


@router.post(
    "/devices/incoming",
    response_model=IncomingMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def report_incoming_sms(
    payload: IncomingSmsReportRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    device: GatewayDevice = Depends(get_current_device),
    db: Session = Depends(get_db),
):
    """
    Called by Android incoming SMS broadcast receiver / worker to synchronize
    a message received on the phone's physical SIM card with the backend.
    Automatically enqueues real-time Google AI Studio auto-reply if enabled.
    """
    try:
        incoming, is_duplicate = ingest_incoming_sms(db, device, payload)
        if is_duplicate:
            response.status_code = status.HTTP_200_OK
        else:
            # Trigger background AI processing and reply dispatch
            if settings.AI_AUTO_REPLY_ENABLED:
                background_tasks.add_task(process_incoming_sms_with_ai, incoming.id)

        return incoming
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/incoming/test-ai-reply",
    response_model=TestAiReplyResponse,
    summary="Test Google AI Studio (Gemini) auto-reply generation",
)
def test_ai_reply(
    payload: TestAiReplyRequest,
    db: Session = Depends(get_db),
):
    """
    Allows developers/administrators to test their GEMINI_API_KEY and prompt
    without requiring an active physical handset.
    """
    if not settings.GEMINI_API_KEY:
        return TestAiReplyResponse(
            status="unconfigured",
            reply=None,
            model=settings.GEMINI_MODEL,
            length=0,
            configured=False,
            note="GEMINI_API_KEY is not set in backend/.env. Please paste your Google AI Studio API key.",
        )

    reply = generate_gemini_reply(
        prompt=payload.message,
        system_instruction=payload.system_instruction or settings.AI_SYSTEM_PROMPT,
    )

    if not reply:
        return TestAiReplyResponse(
            status="error",
            reply=None,
            model=settings.GEMINI_MODEL,
            length=0,
            configured=True,
            note="Failed to generate reply. Check your GEMINI_API_KEY validity or network access.",
        )

    return TestAiReplyResponse(
        status="success",
        reply=reply,
        model=settings.GEMINI_MODEL,
        length=len(reply),
        configured=True,
        note="AI auto-reply generated successfully.",
    )


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
