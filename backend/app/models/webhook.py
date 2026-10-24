import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict
from sqlalchemy import String, Boolean, Integer, Text, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(String(64), nullable=False)
    events: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    deliveries: Mapped[List["WebhookDelivery"]] = relationship(
        "WebhookDelivery", back_populates="subscription", cascade="all, delete-orphan", order_by="desc(WebhookDelivery.created_at)"
    )


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    subscription_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Status: 'pending', 'delivered', 'failed'
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    response_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True, nullable=False
    )

    subscription: Mapped["WebhookSubscription"] = relationship("WebhookSubscription", back_populates="deliveries")

    __table_args__ = (
        Index("ix_deliveries_pending", "status", "next_retry_at"),
    )
