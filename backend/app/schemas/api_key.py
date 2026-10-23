from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import List, Optional


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Friendly label for the API client")
    scopes: List[str] = Field(
        default=["sms:send", "sms:read", "incoming:read", "webhooks:manage"],
        description="Allowed permission scopes"
    )
    rate_limit: int = Field(default=60, ge=1, le=1000, description="Max requests per minute")
    expires_in_days: Optional[int] = Field(default=None, ge=1, description="Optional key validity in days")


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: List[str]
    is_active: bool
    rate_limit: int
    created_at: datetime
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    raw_key: Optional[str] = Field(None, description="Only provided once upon creation")

    model_config = ConfigDict(from_attributes=True)
