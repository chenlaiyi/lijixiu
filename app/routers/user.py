from pydantic import BaseModel
"""用户路由"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user, require_admin, require_staff, require_staff_or_self
from ..core.database import get_db
from ..models.user import BusinessRole, User
from ..schemas.user import UserCreate, UserOut, UserUpdate
from ..services import user as user_service

router = APIRouter(prefix="/api/v1/users", tags=["用户"])


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),  # 2026-10-05:建号只允许平台管理员
):
    from ..core.config import settings
    if not (settings.DEBUG and settings.ALLOW_DEMO_LOGIN):
        raise HTTPException(403, "新用户请通过微信手机号注册")
    existing = await user_service.get_user_by_phone(db, data.phone)
    if existing:
        raise HTTPException(400, "手机号已注册")
    return await user_service.create_user(db, data)


@router.get("", response_model=list[UserOut])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    role: str | None = None,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),  # 2026-10-05:用户名单含手机号,仅内部角色
):
    return await user_service.list_users(db, skip, limit, role)


@router.get("/lookup")
async def lookup_customer(phone: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if not set(user.business_roles) & {"platform_admin", "store_manager", "city_manager", "repairer", "second_receiver", "promotion_manager", "tech_support"}:
        raise HTTPException(403, "仅业务人员可按手机号查询客户")
    target = await user_service.get_user_by_phone(db, phone)
    if not target or "customer" not in target.business_roles or not target.is_active:
        raise HTTPException(404, "客户尚未注册，请先通过微信手机号完成注册")
    return {"id": target.id, "phone": target.phone, "name": target.name}


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05:仅本人或内部角色
):
    require_staff_or_self(user_id, user)
    target = await user_service.get_user(db, user_id)
    if not target:
        raise HTTPException(404, "用户不存在")
    return target


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05:仅本人或内部角色
):
    require_staff_or_self(user_id, user)
    # 2026-10-05:business_role / is_promotion_manager 是权限字段,只有平台管理员能动。
    # 之前任何人都能 PATCH 自己的 business_role 直接提权成 platform_admin。
    if user.id == user_id and not _is_admin(user):
        if data.business_role is not None and data.business_role.value != user.business_role:
            raise HTTPException(403, "cannot change your own business_role")
        if data.is_promotion_manager is not None and data.is_promotion_manager != user.is_promotion_manager:
            raise HTTPException(403, "cannot change your own promotion flag")
    elif not _is_admin(user):
        if data.business_role is not None or data.is_promotion_manager is not None:
            raise HTTPException(403, "admin only for role changes")

    target = await user_service.get_user(db, user_id)
    if not target:
        raise HTTPException(404, "用户不存在")
    if target.phone in {f"1880000000{i}" for i in range(9)} | {"18800000999"}:
        if data.name is not None and data.name != target.name or data.business_role is not None and data.business_role.value != target.business_role or data.is_promotion_manager is not None and data.is_promotion_manager != target.is_promotion_manager:
            raise HTTPException(403, "基础账号的用户名及角色保持不变")
    if data.business_role is not None:
        from ..models.user import UserRole
        role = data.business_role.value
        target.role = UserRole.REPAIRER if role in {"repairer", "second_receiver"} else UserRole.CUSTOMER if role in {"customer", "promotion_manager"} else UserRole.ADMIN
        target.auth_version += 1
    return await user_service.update_user(db, target, data)


def _is_admin(user: User) -> bool:
    return user.business_role == BusinessRole.PLATFORM_ADMIN.value


from pydantic import BaseModel

class AccountStatusRequest(BaseModel):
    is_active: bool

@router.patch("/{user_id}/account-status", response_model=UserOut)
async def account_status(user_id: int, data: AccountStatusRequest,
                         db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    target = await user_service.get_user(db, user_id)
    if not target:
        raise HTTPException(404, "用户不存在")
    if target.id == admin.id and not data.is_active:
        raise HTTPException(400, "不能停用当前管理员账号")
    if target.is_active != data.is_active:
        target.is_active = data.is_active
        target.auth_version += 1
        await db.commit()
        await db.refresh(target)
        from ..core.logging import get_audit_logger
        get_audit_logger().info("account status changed", extra={"actor_user_id": admin.id, "target_user_id": target.id, "is_active": target.is_active})
    return target


from typing import Literal
from pydantic import Field
import json

class BusinessRolesRequest(BaseModel):
    roles: list[Literal['store_manager', 'repairer', 'promotion_manager']] = Field(max_length=3)

@router.patch('/{user_id}/business-roles', response_model=UserOut)
async def assign_business_roles(user_id: int, data: BusinessRolesRequest, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    target = await user_service.get_user(db, user_id)
    if not target: raise HTTPException(404, '用户不存在')
    previous_roles = target.business_roles
    roles = list(dict.fromkeys(data.roles))
    fixed = target.phone in {f'1880000000{i}' for i in range(9)} | {'18800000999'}
    if not fixed and target.business_role in {'customer','store_manager','repairer','promotion_manager'}:
        target.business_role = next((r for r in ['store_manager','repairer','promotion_manager'] if r in roles), 'customer')
    target.extra_roles_json = json.dumps(roles)
    target.is_promotion_manager = target.business_role == 'promotion_manager' or 'promotion_manager' in roles
    from ..models.user import UserRole
    target.role = UserRole.ADMIN if set(target.business_roles) & {'store_manager','city_manager','platform_admin','tech_support','finance','second_receiver'} else UserRole.REPAIRER if 'repairer' in target.business_roles else UserRole.CUSTOMER
    from ..services.repairer import ensure_role_profiles
    await ensure_role_profiles(db, target)
    target.auth_version += 1
    await db.commit()
    await db.refresh(target)
    from ..core.logging import get_audit_logger
    get_audit_logger().info("business identities changed", extra={"actor_user_id":admin.id,"target_user_id":target.id,"before_roles":previous_roles,"after_roles":target.business_roles})
    return target


class ActiveRoleRequest(BaseModel):
    business_role: str

@router.post("/{user_id}/switch-active-role", response_model=UserOut)
async def switch_active_role(user_id: int, data: ActiveRoleRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if user.id != user_id:
        raise HTTPException(403, "只能切换自己的身份")
    if data.business_role not in user.business_roles:
        raise HTTPException(403, "未拥有该身份")
    user.active_business_role = data.business_role
    await db.commit()
    await db.refresh(user)
    return user
