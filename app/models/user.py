"""User model."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UserRole(str, enum.Enum):
    CUSTOMER = "customer"
    REPAIRER = "repairer"
    ADMIN = "admin"


class BusinessRole(str, enum.Enum):
    CUSTOMER = "customer"
    REPAIRER = "repairer"
    STORE_MANAGER = "store_manager"
    SECOND_RECEIVER = "second_receiver"
    PROMOTION_MANAGER = "promotion_manager"
    CITY_MANAGER = "city_manager"
    TECH_SUPPORT = "tech_support"
    FINANCE = "finance"
    PLATFORM_ADMIN = "platform_admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(50))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.CUSTOMER)
    business_role: Mapped[str] = mapped_column(
        String(30), default=BusinessRole.CUSTOMER.value, index=True
    )
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    wechat_openid: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True, index=True
    )
    promotion_manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    is_promotion_manager: Mapped[bool] = mapped_column(Boolean, default=False)
    # 2026-08-09: 鍗忚鐗堟湰绠＄悊(銆婁釜淇濇硶銆嬭姹?娉曞姟鍚堣)
    agreed_terms_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    agreed_privacy_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    agreed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 2026-08-09: 璐︽埛鍒犻櫎鐢宠(15 鏃ュ闄愭湡)
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deletion_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 2026-08-14: 每次登录写一次,解决"系统不知道有没有人登录"的产品债
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def has_wechat_openid(self) -> bool:
        return bool(self.wechat_openid)

    @property
    def is_pending_deletion(self) -> bool:
        return self.deletion_scheduled_at is not None
