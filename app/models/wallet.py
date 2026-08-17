"""Wallet model - one wallet per user."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Wallet(Base):
    """User funds account, separated into available + frozen balance."""

    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), unique=True, comment="User id (1:1)"
    )
    available_balance: Mapped[float] = mapped_column(
        Float, default=0.0, comment="Available (withdrawable) balance"
    )
    frozen_balance: Mapped[float] = mapped_column(
        Float, default=0.0, comment="Frozen balance (in-flight withdrawal)"
    )
    total_income: Mapped[float] = mapped_column(
        Float, default=0.0, comment="Cumulative income (lifetime)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
