import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy import String, Integer, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class SmsBundle(Base):
    __tablename__ = "sms_bundles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)

    plan_name: Mapped[str] = mapped_column(String(100), default="Business SMS Pro", nullable=False)
    total_credits: Mapped[int] = mapped_column(Integer, default=5000, nullable=False)
    used_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_credits: Mapped[int] = mapped_column(Integer, default=5000, nullable=False)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) + timedelta(days=30),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
