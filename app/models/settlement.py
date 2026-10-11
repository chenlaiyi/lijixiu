"""Monthly settlement records for wages and commissions."""

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, enum_column


class SettlementStatus(str, enum.Enum):
    GENERATED = "generated"
    STORE_REVIEW = "store_review"
    CITY_REVIEW = "city_review"
    FINANCE_REVIEW = "finance_review"
    ADMIN_CONFIRM = "admin_confirm"
    PAID = "paid"
    REJECTED = "rejected"


class SettlementItemType(str, enum.Enum):
    TECHNICIAN_WAGE = "technician_wage"
    STORE_MANAGER_COMMISSION = "store_manager_commission"
    CITY_MANAGER_COMMISSION = "city_manager_commission"
    CHANNEL_MANAGER_COMMISSION = "channel_manager_commission"
    TECH_SUPPORT = "tech_support"


class SettlementPeriod(Base):
    __tablename__ = "settlement_periods"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    month: Mapped[str] = mapped_column(String(7), unique=True, index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[SettlementStatus] = mapped_column(
        enum_column(SettlementStatus), default=SettlementStatus.GENERATED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SettlementItem(Base):
    __tablename__ = "settlement_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("settlement_periods.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    item_type: Mapped[SettlementItemType] = mapped_column(enum_column(SettlementItemType))
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[SettlementStatus] = mapped_column(
        enum_column(SettlementStatus), default=SettlementStatus.GENERATED
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
