import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    bundle_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    message_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)

    # Transaction type: 'topup', 'deduction', 'refund', 'admin_adjustment'
    tx_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # Signed integer: positive for topup/refund, negative for deduction
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True, nullable=False
    )
