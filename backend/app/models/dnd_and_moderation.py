import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Boolean, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class DndBlacklist(Base):
    __tablename__ = "dnd_blacklist"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)  # Null = Global block
    phone_number: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # user_opt_out (from incoming SMS STOP/ONDOA), admin_block, invalid_number
    reason: Mapped[str] = mapped_column(String(50), default="user_opt_out", nullable=False)
    source_incoming_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True, nullable=False
    )


class ContentModerationRule(Base):
    __tablename__ = "content_moderation_rules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    pattern: Mapped[str] = mapped_column(String(500), nullable=False)  # Regex pattern
    # action: 'hold_for_approval', 'reject', 'auto_replace'
    action: Mapped[str] = mapped_column(String(30), default="hold_for_approval", nullable=False)
    replacement_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
