"""Order revenue allocation records."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, enum_column


class ProfitRole(str, enum.Enum):
    STORE_REVENUE = "store_revenue"                  # 85%
    STORE_MANAGER_COMMISSION = "store_manager_commission"  # 5%
    CITY_MANAGER_COMMISSION = "city_manager_commission"    # 2%
    CHANNEL_MANAGER_COMMISSION = "channel_manager_commission"  # 1.5%
    TECH_SUPPORT = "tech_support"                  # 3%
    REFERRAL_REWARD = "referral_reward"            # 1%
    PROXY_ASSIST_REWARD = "proxy_assist_reward"    # 1%, proxy orders only
    TECHNICIAN_WAGE = "technician_wage"            # carved out of store revenue
    PASS_THROUGH = "pass_through"                  # excluded from commission calculation
    PLATFORM_RETAINED = "platform_retained"        # 2.5%, or 1.5% for proxy orders


class ProfitStatus(str, enum.Enum):
    PENDING = "pending"
    SETTLED = "settled"


PROFIT_RATIOS: dict[ProfitRole, float] = {
    ProfitRole.STORE_REVENUE: 85.0,
    ProfitRole.STORE_MANAGER_COMMISSION: 5.0,
    ProfitRole.CITY_MANAGER_COMMISSION: 2.0,
    ProfitRole.CHANNEL_MANAGER_COMMISSION: 1.5,
    ProfitRole.TECH_SUPPORT: 3.0,
    ProfitRole.REFERRAL_REWARD: 1.0,
    ProfitRole.PROXY_ASSIST_REWARD: 1.0,
    ProfitRole.PLATFORM_RETAINED: 2.5,
}

# 历史枚举名 → 当前成员名(2026-10-05)。
# 旧版 ProfitRole 用过 REPAIRER / REGION_MANAGER / PROMOTION_MANAGER / PLATFORM
# 等名字,库里已有这些行;读取时映射到当前语义最近的成员,避免 LookupError 500。
LEGACY_PROFIT_ROLE_ALIASES: dict[str, str] = {
    "REPAIRER": "TECHNICIAN_WAGE",
    "REGION_MANAGER": "CITY_MANAGER_COMMISSION",
    "PROMOTION_MANAGER": "REFERRAL_REWARD",
    "PLATFORM": "PLATFORM_RETAINED",
    "PLATFORM_FEE": "PLATFORM_RETAINED",
    "TECH_SUPPORT": "TECH_SUPPORT",
    "STORE": "STORE_REVENUE",
}


class ProfitShare(Base):
    __tablename__ = "profit_shares"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
    role_type: Mapped[ProfitRole] = mapped_column(
        enum_column(ProfitRole, aliases=LEGACY_PROFIT_ROLE_ALIASES)
    )
    amount: Mapped[float] = mapped_column(Float)
    ratio: Mapped[float] = mapped_column(Float)
    status: Mapped[ProfitStatus] = mapped_column(
        enum_column(ProfitStatus), default=ProfitStatus.PENDING
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
