import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ChatAiPreference(Base):
    """
    Controls AI auto-reply and contact blocking behavior per phone number/contact.
    - is_ai_enabled: Whether AI is allowed to reply to this contact.
    - is_blocked: Whether the user/sender is blocked entirely.
    - is_escalated: True if user requested human owner communication.
    """
    __tablename__ = "chat_ai_preferences"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    phone_number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    contact_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_escalated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_chat_pref_phone", "phone_number"),
    )
