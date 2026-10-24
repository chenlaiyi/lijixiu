"""User model."""

import enum
import json
from datetime import datetime

from sqlalchemy import Integer, Text, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, enum_column


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


ALL_BUSINESS_ROLES: tuple[str, ...] = tuple(item.value for item in BusinessRole)

# Role -> legacy UserRole. Used to keep `users.role` meaningful (token payload,
# require_roles fallbacks) for accounts that hold more than one business role.
USER_ROLE_BY_BUSINESS_ROLE: dict[str, "UserRole"] = {
    BusinessRole.PLATFORM_ADMIN.value: UserRole.ADMIN,
    BusinessRole.STORE_MANAGER.value: UserRole.ADMIN,
    BusinessRole.CITY_MANAGER.value: UserRole.ADMIN,
    BusinessRole.TECH_SUPPORT.value: UserRole.ADMIN,
    BusinessRole.FINANCE.value: UserRole.ADMIN,
    BusinessRole.REPAIRER.value: UserRole.REPAIRER,
    BusinessRole.SECOND_RECEIVER.value: UserRole.REPAIRER,
    BusinessRole.PROMOTION_MANAGER.value: UserRole.CUSTOMER,
    BusinessRole.CUSTOMER.value: UserRole.CUSTOMER,
}


def normalize_business_roles(*values: object) -> list[str]:
    """Coerce arbitrary input into a deduped, ordered list of valid roles.

    Accepts BusinessRole members, "store_manager" style values and iterables of
    either. Unknown values are dropped; the result preserves first-seen order so
    the UI shows roles in the order the admin ticked them.
    """
    flat: list[object] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set, frozenset)):
            flat.extend(value)
        else:
            flat.append(value)

    result: list[str] = []
    for item in flat:
        if isinstance(item, BusinessRole):
            candidate = item.value
        else:
            candidate = str(item or "").strip().lower()
        if candidate in ALL_BUSINESS_ROLES and candidate not in result:
            result.append(candidate)
    return result


def required_user_role(roles: list[str]) -> "UserRole":
    """Pick the legacy UserRole that best represents this role set."""
    for value in ALL_BUSINESS_ROLES:
        if value in roles:
            mapped = USER_ROLE_BY_BUSINESS_ROLE.get(value)
            if mapped is not None:
                return mapped
    return UserRole.CUSTOMER


class UserRoleGrant(Base):
    """Append-only audit log of business-role assignment changes.

    2026-10-07 multi-role: `users.business_roles` holds the current set; this
    table answers "who gave this account that role, and when".
    """

    __tablename__ = "user_role_grants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    business_role: Mapped[str] = mapped_column(String(30), index=True)
    action: Mapped[str] = mapped_column(String(20), default="grant")  # grant/revoke/set
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    operator_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="admin")  # admin/login/system
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(50))
    role: Mapped[UserRole] = mapped_column(enum_column(UserRole), default=UserRole.CUSTOMER)
    business_role: Mapped[str] = mapped_column(
        String(30), default=BusinessRole.CUSTOMER.value, index=True
    )
    active_business_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    extra_roles_json: Mapped[str | None] = mapped_column(String(256), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    auth_version: Mapped[int] = mapped_column(Integer, default=0)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    wechat_openid: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True, index=True
    )
    referrer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    referral_code: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True, index=True)
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

    @property
    def business_roles(self) -> list[str]:
        try:
            extras = json.loads(self.extra_roles_json or '[]')
        except (ValueError, TypeError):
            extras = []
        permitted = {'store_manager', 'repairer', 'promotion_manager'}
        roles = [self.business_role or 'customer'] + [r for r in extras if r in permitted]
        if self.is_promotion_manager: roles.append('promotion_manager')
        if self.business_role != 'platform_admin': roles.append('customer')
        return list(dict.fromkeys(roles))

    @business_roles.setter
    def business_roles(self, values):
        roles = normalize_business_roles(values)
        self.business_role = roles[0] if roles else 'customer'
        self.extra_roles_json = json.dumps(roles[1:])

    def grant_business_role(self, role: str) -> None:
        if self.business_role == 'platform_admin': return
        if role in {'store_manager','repairer','promotion_manager'}:
            extras = [r for r in self.business_roles if r in {'store_manager','repairer','promotion_manager'}]
            self.extra_roles_json = json.dumps(list(dict.fromkeys(extras + [role])))
            if self.business_role == 'customer': self.business_role = role
        elif self.business_role != role:
            self.business_role = role
        self.is_promotion_manager = 'promotion_manager' in self.business_roles
        self.role = UserRole.ADMIN if set(self.business_roles) & {'store_manager','city_manager','platform_admin','tech_support','finance'} else UserRole.REPAIRER if set(self.business_roles) & {'repairer','second_receiver'} else UserRole.CUSTOMER
