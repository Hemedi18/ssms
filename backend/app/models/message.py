import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)

    to: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    original_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Status: 'pending_approval', 'scheduled', 'queued', 'dispatched', 'sending', 'sent', 'delivered', 'failed', 'rejected', 'cancelled'
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True, nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), default="transactional", nullable=False)  # transactional, promotional
    priority: Mapped[int] = mapped_column(Integer, default=10, nullable=False)  # 10 for OTP, 1 for bulk promo
    encoding: Mapped[str] = mapped_column(String(20), default="GSM_7BIT", nullable=False)  # GSM_7BIT, UCS_2
    detected_mno: Mapped[str] = mapped_column(String(30), default="UNKNOWN", nullable=False)

    client_reference: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)

    # Assigned device & leasing lock
    device_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    lease_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    leased_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    sender_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sim_slot: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    parts_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Admin oversight & notes
    modified_by_admin_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Scheduling (TCRA quiet hours or user schedule)
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True, nullable=True)

    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    events: Mapped[List["MessageEvent"]] = relationship(
        "MessageEvent", back_populates="message", cascade="all, delete-orphan", order_by="MessageEvent.created_at"
    )

    __table_args__ = (
        Index("ix_messages_status_created_at", "status", "created_at"),
        Index("ix_messages_priority_created", "priority", "created_at"),
        Index("ix_messages_tenant_status", "tenant_id", "status"),
    )


class MessageEvent(Base):
    __tablename__ = "message_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    error_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    message: Mapped["Message"] = relationship("Message", back_populates="events")
