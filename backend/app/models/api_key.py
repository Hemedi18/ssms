import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Boolean, Integer, DateTime, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rate_limit: Mapped[int] = mapped_column(Integer, default=60, nullable=False)

    # IP Whitelisting: Comma-separated list of IPv4/IPv6 addresses or CIDRs (e.g., '192.168.1.0/24, 203.0.113.10')
    allowed_ips: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def has_scope(self, scope: str) -> bool:
        return "admin" in self.scopes or scope in self.scopes
