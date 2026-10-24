from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List, Dict, Any


class SimSlotTelemetry(BaseModel):
    slot: int = Field(..., ge=0, le=3, description="0 for SIM 1, 1 for SIM 2")
    carrier: Optional[str] = None
    number: Optional[str] = None
    daily_sent: int = 0
    limit: int = 500
    signal_level: Optional[int] = None


class DevicePairRequest(BaseModel):
    pairing_code: str = Field(..., min_length=4, max_length=32, description="Pairing code from server")
    device_name: str = Field("Android Device", max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    os_version: Optional[str] = Field(None, max_length=50)
    app_version: Optional[str] = Field(None, max_length=30)
    tenant_id: Optional[str] = None


class DevicePairResponse(BaseModel):
    device_id: str
    device_token: str
    name: str
    message: str = "Pairing successful. Use device_token as Bearer token for device endpoints."


class DeviceHeartbeatRequest(BaseModel):
    sim_ready: bool = Field(..., description="Whether a functional SIM is detected and accessible")
    phone_number: Optional[str] = Field(None, description="Reported SIM phone number if available")
    carrier_name: Optional[str] = Field(None, description="Mobile carrier name (e.g. Vodacom, Airtel, Tigo)")
    network_type: Optional[str] = Field(None, description="e.g. LTE, 5G, Wi-Fi")
    signal_level: Optional[int] = Field(None, ge=0, le=4, description="Signal strength level 0-4")
    battery_level: Optional[int] = Field(None, ge=0, le=100, description="Battery percentage 0-100")
    sim_slots: Optional[List[SimSlotTelemetry]] = Field(None, description="Dual-SIM slot telemetry")


class GatewayDeviceResponse(BaseModel):
    id: str
    tenant_id: Optional[str] = None
    name: str
    model: Optional[str] = None
    os_version: Optional[str] = None
    app_version: Optional[str] = None
    sim_ready: bool
    phone_number: Optional[str] = None
    carrier_name: Optional[str] = None
    network_type: Optional[str] = None
    signal_level: Optional[int] = None
    battery_level: Optional[int] = None
    is_shared_pool: bool = True
    max_sms_per_30_min: int = 28
    sim_slots_telemetry: Optional[List[Dict[str, Any]]] = None
    is_online: bool
    last_seen_at: Optional[datetime] = None
    is_revoked: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeviceJobResponse(BaseModel):
    job_id: str
    message_id: str
    to: str
    body: str
    lease_token: str
    parts_count: int = 1
    sim_slot: Optional[int] = None
    priority: int = 10
    encoding: str = "GSM_7BIT"
    created_at: datetime


class DeviceSendResultRequest(BaseModel):
    status: str = Field(..., pattern="^(sent|delivered|failed)$", description="Result status")
    error_message: Optional[str] = None
    parts_sent: Optional[int] = 1
    timestamp: Optional[datetime] = None
