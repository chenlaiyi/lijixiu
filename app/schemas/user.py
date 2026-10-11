"""User schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from ..models.user import BusinessRole, UserRole


class UserCreate(BaseModel):
    phone: str = Field(min_length=11, max_length=20, examples=["13800138000"])
    name: str = Field(min_length=1, max_length=50)
    role: UserRole = UserRole.CUSTOMER
    business_role: BusinessRole = BusinessRole.CUSTOMER
    # 2026-10-07 multi-role:可一次建号就带上多个角色;留空则用 business_role。
    business_roles: list[BusinessRole] | None = None
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
    # 2026-10-07 multi-role:整体替换角色集合(仅平台管理员可写)。
    business_roles: list[BusinessRole] | None = None


class UserOut(BaseModel):
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


# 2026-10-07 multi-role:角色管理接口
class RoleAssignmentRequest(BaseModel):
    """整体替换某个账号拥有的业务角色集合。"""

    business_roles: list[BusinessRole] = Field(min_length=1)
    active_business_role: BusinessRole | None = None
    remark: str | None = Field(None, max_length=200)


class SwitchRoleRequest(BaseModel):
    """用户自己切换当前身份,只能选自己拥有的角色。"""

    business_role: BusinessRole
    remark: str | None = Field(None, max_length=200)


class RoleGrantOut(BaseModel):
    id: int
    business_role: str
    role_label: str
    action: str
    source: str
    operator_id: int | None = None
    operator_name: str | None = None
    remark: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class RoleOptionOut(BaseModel):
    value: str
    label: str
    staff: bool = False
    workbench: bool = False


class UserRolesOut(BaseModel):
    """GET /api/v1/users/{id}/roles —— 小程序「我的」页与后台都用它渲染。"""

    user_id: int
    phone: str
    name: str
    business_roles: list[str]
    active_business_role: str
    active_role_label: str
    business_role: str
    role_labels: list[str]
    workbench_roles: list[str]
    can_switch: bool
    history: list[RoleGrantOut] = Field(default_factory=list)


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
