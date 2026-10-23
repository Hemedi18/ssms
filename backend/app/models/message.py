import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    to: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Status: 'queued', 'dispatched', 'sending', 'sent', 'delivered', 'failed'
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True, nullable=False)
    client_reference: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)

    # Assigned device & leasing lock
    device_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    parts_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    events: Mapped[list["MessageEvent"]] = relationship(
        "MessageEvent", back_populates="message", cascade="all, delete-orphan", order_by="MessageEvent.created_at"
    )

    __table_args__ = (
        Index("ix_messages_status_created_at", "status", "created_at"),
    )


class MessageEvent(Base):
    __tablename__ = "message_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    message: Mapped["Message"] = relationship("Message", back_populates="events")
