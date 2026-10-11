"""Append-only wallet ledger model."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, enum_column


class LedgerType(str, enum.Enum):
    ORDER_INCOME = "order_income"
    PROFIT_SETTLEMENT = "profit_settlement"
    TECHNICIAN_WAGE = "technician_wage"
    MONTHLY_WAGE_PAYMENT = "monthly_wage_payment"
    REFUND_CLAWBACK = "refund_clawback"
    MANUAL_ADJUST = "manual_adjust"
    WITHDRAWAL = "withdrawal"
    WITHDRAWAL_COMPLETE = "withdrawal_complete"
    WITHDRAWAL_REJECT = "withdrawal_reject"
    # 2026-08-09: 鏂板,鐢ㄤ簬鏍囪"鍐荤粨/瑙ｅ喕"绛夐挶鍖呭唴杞Щ浜嬩欢(ledger amount=0)
    LEDGER_FREEZE = "ledger_freeze"
    LEDGER_UNFREEZE = "ledger_unfreeze"


class Ledger(Base):
    """Wallet balance movement. Rows are append-only."""

    __tablename__ = "ledgers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[LedgerType] = mapped_column(enum_column(LedgerType))
    amount: Mapped[float] = mapped_column(Float)
    balance_after: Mapped[float] = mapped_column(Float)
    reference_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
