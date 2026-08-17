"""Withdrawal model."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class WithdrawalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Withdrawal(Base):
    """A wallet withdrawal request."""

    __tablename__ = "withdrawals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"))
    amount: Mapped[float] = mapped_column(Float)
    status: Mapped[WithdrawalStatus] = mapped_column(
        Enum(WithdrawalStatus), default=WithdrawalStatus.PENDING
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    payout_provider: Mapped[str] = mapped_column(String(20), default="manual")
    payout_status: Mapped[str] = mapped_column(String(30), default="none")
    transfer_out_bill_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    transfer_bill_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    transfer_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    payout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
