from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional


class IncomingSmsReportRequest(BaseModel):
    from_number: str = Field(..., description="Originating sender phone number")
    body: str = Field(..., description="Message text")
    received_at: datetime = Field(..., description="Timestamp message arrived on phone")
    device_message_id: Optional[str] = Field(None, description="Local Room ID on Android device")
    is_multipart: bool = False
    part_index: int = 1
    total_parts: int = 1
    pdu_hash: Optional[str] = None


class IncomingMessageResponse(BaseModel):
    id: str
    device_message_id: Optional[str] = None
    from_number: str
    body: str
    received_at_device: datetime
    is_multipart: bool
    part_index: int
    total_parts: int
    device_id: Optional[str] = None
    synced_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
