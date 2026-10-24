"""User schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from ..models.user import BusinessRole, UserRole


class UserCreate(BaseModel):
    phone: str = Field(min_length=11, max_length=20, examples=["13800138000"])
    name: str = Field(min_length=1, max_length=50)
    role: UserRole = UserRole.CUSTOMER
    business_role: BusinessRole = BusinessRole.CUSTOMER
    avatar: str | None = None
    wechat_openid: str | None = None
    promotion_manager_id: int | None = None
    is_promotion_manager: bool = False


class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    avatar: str | None = None
    wechat_openid: str | None = None
    promotion_manager_id: int | None = None
    is_promotion_manager: bool | None = None
    business_role: BusinessRole | None = None


class UserOut(BaseModel):
    is_active: bool = True
    id: int
    phone: str
    name: str
    role: UserRole
    business_role: str
    business_roles: list[str] = Field(default_factory=list)
    active_business_role: str | None = None
    avatar: str | None
    has_wechat_openid: bool = False
    promotion_manager_id: int | None
    referrer_user_id: int | None = None
    is_promotion_manager: bool
    agreed_terms_version: str | None = None
    agreed_privacy_version: str | None = None
    agreed_at: datetime | None = None
    deletion_requested_at: datetime | None = None
    deletion_scheduled_at: datetime | None = None
    # 2026-08-14: 加 last_login_at 字段 — admin 查活跃用户必备
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# 2026-08-09: 协议同意版本管理
CURRENT_TERMS_VERSION = "v1.0"  # 必须与 docs/legal/user-agreement.md 的版本号一致
CURRENT_PRIVACY_VERSION = "v1.0"  # 必须与 docs/legal/privacy-policy.md 的版本号一致


class AgreementRequest(BaseModel):
    terms_version: str = Field(min_length=1, max_length=20, examples=[CURRENT_TERMS_VERSION])
    privacy_version: str = Field(min_length=1, max_length=20, examples=[CURRENT_PRIVACY_VERSION])


class AgreementStatus(BaseModel):
    terms_version: str
    privacy_version: str
    agreed_terms: str | None = None
    agreed_privacy: str | None = None
    need_renewal: bool
    agreed_at: datetime | None = None
