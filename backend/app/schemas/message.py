from pydantic import BaseModel, Field, ConfigDict, model_validator
from datetime import datetime
from typing import Optional, List, Dict, Any


class MessageCreate(BaseModel):
    to: str = Field(..., description="Destination phone number in E.164 format (e.g. +255712345678)")
    message: Optional[str] = Field(None, description="SMS message text")
    body: Optional[str] = Field(None, description="Alias for message")
    sender_name: Optional[str] = Field(None, max_length=50, description="Custom sender/brand name (e.g. EDUSPHERE)")
    sim_slot: Optional[int] = Field(None, ge=0, le=3, description="Preferred SIM slot (0 for SIM 1, 1 for SIM 2)")
    client_reference: Optional[str] = Field(None, max_length=100, description="Caller's custom reference ID")
    idempotency_key: Optional[str] = Field(None, max_length=64, description="Unique key for duplicate protection")
    webhook_url: Optional[str] = Field(None, max_length=2048, description="Optional ad-hoc webhook callback URL")

    # Multi-tenant & Tanzania routing controls
    message_type: str = Field(default="transactional", description="'transactional' (OTP/alerts) or 'promotional'")
    priority: int = Field(default=10, ge=1, le=100, description="Dispatch priority (10=urgent OTP, 1=bulk promotional)")
    tenant_id: Optional[str] = Field(None, description="Tenant organization UUID")

    @model_validator(mode="before")
    @classmethod
    def check_message_or_body(cls, data: Any) -> Any:
        if isinstance(data, dict):
            text = data.get("message") or data.get("body")
            if not text or not str(text).strip():
                raise ValueError("Either 'message' or 'body' must be provided and not empty")
            data["body"] = str(text).strip()
            data["message"] = str(text).strip()
        return data


class BulkMessageCreate(BaseModel):
    recipients: List[str] = Field(..., min_length=1, max_length=5000, description="List of recipient phone numbers")
    message: Optional[str] = Field(None, description="SMS message text")
    body: Optional[str] = Field(None, description="Alias for message")
    sender_name: Optional[str] = Field(None, max_length=50, description="Brand/sender name (e.g. EDUSPHERE)")
    sim_slot: Optional[int] = Field(None, ge=0, le=3, description="Preferred SIM slot (0 for SIM 1, 1 for SIM 2)")
    anti_spam_delay: float = Field(default=4.0, ge=1.0, le=60.0, description="Delay between sends in seconds")
    randomize_jitter: bool = Field(default=True, description="Add random jitter (+/- 1.5s) to avoid periodic detection")

    # Advanced Multi-tenant, Spintax & Variable Interpolation
    message_type: str = Field(default="promotional", description="'promotional' or 'transactional'")
    priority: int = Field(default=1, ge=1, le=100, description="Priority level")
    variables: Optional[Dict[str, Dict[str, Any]]] = Field(
        None, description="Recipient phone -> variable dictionary (e.g. {'+255...': {'name': 'Juma'}})"
    )
    use_spintax: bool = Field(default=True, description="Enable {Habari|Mambo|Salamu} phrase randomization")
    tenant_id: Optional[str] = Field(None, description="Tenant organization UUID")

    @model_validator(mode="before")
    @classmethod
    def check_message_or_body(cls, data: Any) -> Any:
        if isinstance(data, dict):
            text = data.get("message") or data.get("body")
            if not text or not str(text).strip():
                raise ValueError("Either 'message' or 'body' must be provided and not empty")
            data["body"] = str(text).strip()
            data["message"] = str(text).strip()
        return data


class BulkMessageResponse(BaseModel):
    total_recipients: int
    valid_recipients: int
    duplicates_removed: int
    invalid_recipients: int
    queued_messages: int
    credits_deducted: int
    remaining_credits: int
    estimated_time_minutes: float
    message_ids: List[str]
    message: str
    quarantined_count: int = 0
    mno_breakdown: Optional[Dict[str, int]] = None


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
    tenant_id: Optional[str] = None
    to: str
    body: str
    original_body: Optional[str] = None
    status: str
    message_type: str = "transactional"
    priority: int = 10
    encoding: str = "GSM_7BIT"
    detected_mno: str = "UNKNOWN"
    sender_name: Optional[str] = None
    sim_slot: Optional[int] = None
    client_reference: Optional[str] = None
    idempotency_key: Optional[str] = None
    device_id: Optional[str] = None
    parts_count: int
    error_message: Optional[str] = None
    modified_by_admin_id: Optional[str] = None
    admin_notes: Optional[str] = None
    scheduled_for: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    events: Optional[List[MessageEventResponse]] = None

    model_config = ConfigDict(from_attributes=True)


class MessageFilterParams(BaseModel):
    status: Optional[str] = None
    to: Optional[str] = None
    tenant_id: Optional[str] = None
    message_type: Optional[str] = None
    detected_mno: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class MessageModifyRequest(BaseModel):
    body: Optional[str] = Field(None, min_length=1, description="Edited SMS body")
    sender_name: Optional[str] = Field(None, max_length=50)
    to: Optional[str] = Field(None, description="New recipient phone number")
    sim_slot: Optional[int] = Field(None, ge=0, le=3)
    priority: Optional[int] = Field(None, ge=1, le=100)
    admin_notes: Optional[str] = Field(None, description="Reason for modification")


class BatchActionRequest(BaseModel):
    message_ids: List[str] = Field(..., min_length=1, max_length=1000)
    action: str = Field(..., description="'approve', 'reject', 'cancel', 'force_reroute'")
    target_sim_slot: Optional[int] = Field(None, ge=0, le=3)
    target_device_id: Optional[str] = None
    new_sender_name: Optional[str] = None
    admin_notes: Optional[str] = None


class BatchActionResponse(BaseModel):
    action: str
    affected_count: int
    credits_refunded: int
    message: str
