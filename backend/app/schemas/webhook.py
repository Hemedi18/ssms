from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import List, Optional, Any, Dict

SUPPORTED_EVENTS = [
    "sms.queued",
    "sms.sent",
    "sms.delivered",
    "sms.failed",
    "sms.received",
    "device.online",
    "device.offline",
]


class WebhookSubscriptionCreate(BaseModel):
    url: str = Field(..., description="Destination webhook HTTPS/HTTP URL")
    events: List[str] = Field(
        default=SUPPORTED_EVENTS,
        description="List of event names to subscribe to"
    )
    secret: Optional[str] = Field(None, description="Optional custom signing secret. Auto-generated if omitted.")


class WebhookSubscriptionUpdate(BaseModel):
    url: Optional[str] = None
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None


class WebhookSubscriptionResponse(BaseModel):
    id: str
    url: str
    events: List[str]
    is_active: bool
    secret: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebhookDeliveryResponse(BaseModel):
    id: str
    subscription_id: str
    event_id: str
    event_type: str
    status: str
    attempts: int
    response_status_code: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    next_retry_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebhookEventPayload(BaseModel):
    id: str
    type: str
    created_at: datetime
    data: Dict[str, Any]
