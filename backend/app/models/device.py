import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Boolean, Integer, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class GatewayDevice(Base):
    __tablename__ = "gateway_devices"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    is_shared_pool: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_sms_per_30_min: Mapped[int] = mapped_column(Integer, default=28, nullable=False)

    device_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    os_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    app_version: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # Hardware & Telephony Diagnostics
    sim_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone_number: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    carrier_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    network_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    signal_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    battery_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Dual-SIM Telemetry (slot details, rolling counts, limits)
    sim_slots_telemetry: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Connectivity State
    is_online: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class PairingCode(Base):
    __tablename__ = "pairing_codes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    device_name: Mapped[str] = mapped_column(String(100), default="Android Gateway Device", nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
