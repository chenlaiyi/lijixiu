"""Wallet reconciliation log model."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ReconcileStatus(str, enum.Enum):
    OK = "ok"
    MISMATCH = "mismatch"


class ReconciliationLog(Base):
    """Daily reconciliation row comparing ledger sum vs wallet.available_balance."""

    __tablename__ = "reconciliation_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id"), index=True, comment="Wallet id"
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, comment="User id"
    )
    expected_balance: Mapped[float] = mapped_column(
        Float, comment="Sum of all ledger amounts (the expected wallet balance)"
    )
    actual_balance: Mapped[float] = mapped_column(
        Float, comment="wallet.available_balance at reconciliation time"
    )
    difference: Mapped[float] = mapped_column(
        Float, comment="ledger_sum - wallet_available"
    )
    status: Mapped[ReconcileStatus] = mapped_column(
        Enum(ReconcileStatus, name="reconcilestatus"),
        comment="ok | mismatch",
    )
    detail: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Mismatch detail (drill-down JSON)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
