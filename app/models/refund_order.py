"""Refund order model."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, enum_column


class RefundStatus(str, enum.Enum):
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    CLOSED = "closed"


class RefundOrder(Base):
    """A WeChat original-route refund request for a pay order."""

    __tablename__ = "refund_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pay_order_id: Mapped[int] = mapped_column(ForeignKey("pay_orders.id"), index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[RefundStatus] = mapped_column(
        enum_column(RefundStatus), default=RefundStatus.PROCESSING, index=True
    )
    out_refund_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    refund_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    notify_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
