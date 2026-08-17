"""Service bill submitted by a technician after on-site confirmation."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ServiceBillStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    RETURNED = "returned"
    CONFIRMED = "confirmed"


class ServiceBill(Base):
    __tablename__ = "service_bills"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    repairer_id: Mapped[int] = mapped_column(ForeignKey("repairers.id"), index=True)
    title: Mapped[str] = mapped_column(String(120), default="Service bill")
    items_json: Mapped[str] = mapped_column(Text, default="[]")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    warranty_days: Mapped[int] = mapped_column(Integer, default=0)
    media_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ServiceBillStatus] = mapped_column(
        Enum(ServiceBillStatus), default=ServiceBillStatus.SUBMITTED
    )
    return_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    confirmation_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    confirmation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
