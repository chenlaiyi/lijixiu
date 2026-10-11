"""用户路由"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user, require_admin, require_staff, require_staff_or_self
from ..core.database import get_db
from ..core.logging import get_audit_logger
from ..models.user import (
    ALL_BUSINESS_ROLES,
    BusinessRole,
    User,
    normalize_business_roles,
)
from ..schemas.user import (
    RoleAssignmentRequest,
    SwitchRoleRequest,
    UserCreate,
    UserOut,
    UserRolesOut,
    UserUpdate,
)
from ..services import role as role_service
from ..services import user as user_service

router = APIRouter(prefix="/api/v1/users", tags=["用户"])

audit_log = get_audit_logger()


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),  # 2026-10-05:建号只允许平台管理员
):
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


@router.get("/roles/options")
async def list_role_options(
    _user: User = Depends(get_current_user),
) -> list[dict]:
    """可分配的业务角色字典(小程序与后台共用同一份,避免两边硬编码漂移)。"""
    return [
        {
            "value": value,
            "label": role_service.role_label(value),
            "staff": value in role_service.STAFF_ROLES,
            "workbench": value in role_service.WORKBENCH_ROLES,
        }
        for value in ALL_BUSINESS_ROLES
    ]


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


@router.get("/{user_id}/roles", response_model=UserRolesOut)
async def get_user_roles(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """账号拥有的全部角色 + 当前选中角色(小程序「我的」页数据源)。"""
    require_staff_or_self(user_id, user)
    target = await user_service.get_user(db, user_id)
    if not target:
        raise HTTPException(404, "用户不存在")

    roles = role_service.resolve_roles(target)
    active = role_service.active_role(target)
    include_history = role_service.is_staff(user)
    history = await role_service.role_grants(db, target.id) if include_history else []
    return UserRolesOut(
        user_id=target.id,
        phone=target.phone,
        name=target.name,
        business_roles=roles,
        active_business_role=active,
        active_role_label=role_service.role_label(active),
        business_role=target.business_role,
        role_labels=[role_service.role_label(item) for item in roles],
        workbench_roles=[item for item in roles if item in role_service.WORKBENCH_ROLES],
        can_switch=len(roles) > 1,
        history=[
            {
                "id": item.id,
                "business_role": item.business_role,
                "role_label": role_service.role_label(item.business_role),
                "action": item.action,
                "source": item.source,
                "operator_id": item.operator_id,
                "operator_name": item.operator_name,
                "remark": item.remark,
                "created_at": item.created_at,
            }
            for item in history
        ],
    )


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
        if data.business_role is not None and data.business_role.value not in role_service.resolve_roles(user):
            raise HTTPException(403, "cannot change your own business_role")
        if data.business_roles is not None:
            raise HTTPException(403, "cannot change your own business_roles")
        if data.is_promotion_manager is not None and data.is_promotion_manager is not user.is_promotion_manager:
            raise HTTPException(403, "cannot change your own promotion flag")
    elif not _is_admin(user):
        if data.business_role is not None or data.business_roles is not None:
            raise HTTPException(403, "admin only for role changes")
        if data.is_promotion_manager is not None:
            raise HTTPException(403, "admin only for role changes")

    target = await user_service.get_user(db, user_id)
    if not target:
        raise HTTPException(404, "用户不存在")
    return await user_service.update_user(db, target, data)


@router.patch("/{user_id}/roles", response_model=UserRolesOut)
async def assign_user_roles(
    user_id: int,
    data: RoleAssignmentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """平台管理员配置「关联角色」(多选)。

    这是权限的唯一写入口:PATCH /users/{id} 的单角色写法只做叠加,
    想真正收回角色必须走这里。
    """
    target = await user_service.get_user(db, user_id)
    if not target:
        raise HTTPException(404, "用户不存在")

    roles = normalize_business_roles(data.business_roles)
    if not roles:
        raise HTTPException(400, "business_roles 不能为空")
    if target.id == admin.id and BusinessRole.PLATFORM_ADMIN.value not in roles:
        # 防止管理员把自己降权后再也进不来后台
        raise HTTPException(400, "不能移除自己的平台管理员角色")

    before = role_service.resolve_roles(target)
    _, granted, revoked = await role_service.set_roles(
        db,
        target,
        roles,
        operator=admin,
        source="admin",
        remark=data.remark,
    )
    if data.active_business_role is not None:
        target.active_business_role = data.active_business_role.value
    await db.commit()
    await db.refresh(target)

    audit_log.info(
        "角色配置变更",
        extra={
            "request_id": getattr(request.state, "request_id", "-"),
            "trace_id": getattr(request.state, "trace_id", "-"),
            "actor_user_id": admin.id,
            "actor_business_role": admin.business_role,
            "target_user_id": target.id,
            "roles_before": before,
            "roles_after": role_service.resolve_roles(target),
            "granted": granted,
            "revoked": revoked,
        },
    )
    return await get_user_roles(user_id, db=db, user=admin)


@router.post("/{user_id}/switch-active-role", response_model=UserRolesOut)
async def switch_active_role(
    user_id: int,
    data: SwitchRoleRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """本人(或管理员代操作)切换当前生效身份。

    全局切换:小程序首页 / 底部导航 / 工作台 / 数据可见范围都跟着走。
    只能在自己「拥有」的角色里选,不能借此提权。
    """
    require_staff_or_self(user_id, user)
    target = await user_service.get_user(db, user_id)
    if not target:
        raise HTTPException(404, "用户不存在")

    target_role = data.business_role.value
    roles = role_service.resolve_roles(target)
    if target_role not in roles:
        raise HTTPException(
            403,
            f"该账号没有 {target_role} 角色,不能切换(当前:{','.join(roles)})",
        )

    target.active_business_role = target_role
    await db.commit()
    await db.refresh(target)
    return await get_user_roles(user_id, db=db, user=user)


def _is_admin(user: User) -> bool:
    return role_service.is_admin(user)
