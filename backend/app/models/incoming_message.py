import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Integer, Text, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class IncomingMessage(Base):
    __tablename__ = "incoming_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    device_message_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    from_number: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    received_at_device: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    is_multipart: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    part_index: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    total_parts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    raw_pdu_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)

    device_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True, nullable=False
    )

    __table_args__ = (
        Index("ix_incoming_dedup", "from_number", "received_at_device", "raw_pdu_hash"),
    )
