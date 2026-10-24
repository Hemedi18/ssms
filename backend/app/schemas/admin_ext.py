from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., min_length=2, max_length=100)
    can_use_shared_devices: bool = True
    require_bulk_approval_threshold: int = Field(default=200, ge=1)
    allowed_sender_names: List[str] = Field(default_factory=list)
    daily_sms_limit: int = Field(default=10000, ge=10)


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None  # active, suspended
    can_use_shared_devices: Optional[bool] = None
    require_bulk_approval_threshold: Optional[int] = None
    allowed_sender_names: Optional[List[str]] = None
    daily_sms_limit: Optional[int] = None


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    status: str
    can_use_shared_devices: bool
    require_bulk_approval_threshold: int
    allowed_sender_names: List[str]
    daily_sms_limit: int
    created_at: datetime


class UserCreate(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=2)
    role: str = Field(default="tenant_admin", description="super_admin, tenant_admin, tenant_developer, tenant_viewer")
    tenant_id: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    tenant_id: Optional[str]
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login_at: Optional[datetime]
    created_at: datetime


class DndBlacklistCreate(BaseModel):
    phone_number: str
    reason: str = "admin_block"
    tenant_id: Optional[str] = None


class DndBlacklistResponse(BaseModel):
    id: str
    tenant_id: Optional[str]
    phone_number: str
    reason: str
    source_incoming_id: Optional[str]
    created_at: datetime


class ModerationRuleCreate(BaseModel):
    name: str
    pattern: str  # Regex
    action: str = Field("hold_for_approval", description="'hold_for_approval', 'reject', 'auto_replace'")
    replacement_text: Optional[str] = None
    is_active: bool = True


class ModerationRuleResponse(BaseModel):
    id: str
    name: str
    pattern: str
    action: str
    replacement_text: Optional[str]
    is_active: bool
    created_at: datetime


class KillSwitchRequest(BaseModel):
    enabled: bool
    tenant_id: Optional[str] = None
    reason: Optional[str] = None


class KillSwitchResponse(BaseModel):
    global_paused: bool
    paused_tenants: List[str]
    message: str
