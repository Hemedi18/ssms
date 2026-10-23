from pydantic import BaseModel, Field, ConfigDict, model_validator
from datetime import datetime
from typing import Optional, List


class MessageCreate(BaseModel):
    to: str = Field(..., description="Destination phone number in E.164 format (e.g. +255712345678)")
    message: Optional[str] = Field(None, description="SMS message text")
    body: Optional[str] = Field(None, description="Alias for message")
    client_reference: Optional[str] = Field(None, max_length=100, description="Caller's custom reference ID")
    idempotency_key: Optional[str] = Field(None, max_length=64, description="Unique key for duplicate protection")
    webhook_url: Optional[str] = Field(None, max_length=2048, description="Optional ad-hoc webhook callback URL")

    @model_validator(mode="before")
    @classmethod
    def check_message_or_body(cls, data: any) -> any:
        if isinstance(data, dict):
            text = data.get("message") or data.get("body")
            if not text or not str(text).strip():
                raise ValueError("Either 'message' or 'body' must be provided and not empty")
            data["body"] = str(text).strip()
            data["message"] = str(text).strip()
        return data


class MessageEventResponse(BaseModel):
    id: str
    message_id: str
    status: str
    error_details: Optional[str] = None
    device_id: Optional[str] = None
    event_timestamp: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    id: str
    to: str
    body: str
    status: str
    client_reference: Optional[str] = None
    idempotency_key: Optional[str] = None
    device_id: Optional[str] = None
    parts_count: int
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    events: Optional[List[MessageEventResponse]] = None

    model_config = ConfigDict(from_attributes=True)


class MessageFilterParams(BaseModel):
    status: Optional[str] = None
    to: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
