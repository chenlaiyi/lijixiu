"""Multi-role helpers (2026-10-07).

背景:一个手机号(如 18060936373)可能同时是店长、师傅、业务。历史上权限靠
`users.business_role` 这一个字符串,多角色只能三选一。现在:

  * `users.business_roles`  —— 该账号「拥有」的全部业务角色(JSON 数组,唯一真相)
  * `users.active_business_role` —— 用户在小程序「我的」里「当前选中」的角色
  * `users.business_role`   —— 兼容字段,始终等于 business_roles[0]

鉴权口径由本模块统一:只要**拥有**任一所需角色即放行(并集),不要求它正好是
当前选中的角色 —— 否则用户切个身份就会突然 403。

`app/core/auth.py` 只做 HTTP 层包装,判断逻辑全在这里,便于单测与复用。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import (
    ALL_BUSINESS_ROLES,
    BusinessRole,
    User,
    UserRoleGrant,
    normalize_business_roles,
    required_user_role,
)

# Roles that may see platform-internal data (customers must never).
STAFF_ROLES: frozenset[str] = frozenset(
    {
        BusinessRole.PLATFORM_ADMIN.value,
        BusinessRole.STORE_MANAGER.value,
        BusinessRole.CITY_MANAGER.value,
        BusinessRole.TECH_SUPPORT.value,
        BusinessRole.FINANCE.value,
        BusinessRole.SECOND_RECEIVER.value,
    }
)

ADMIN_ROLES: frozenset[str] = frozenset({BusinessRole.PLATFORM_ADMIN.value})

# Roles that can reach a workbench (i.e. anything but a pure customer).
WORKBENCH_ROLES: frozenset[str] = frozenset(ALL_BUSINESS_ROLES) - {
    BusinessRole.CUSTOMER.value
}


def resolve_roles(user: User | None) -> list[str]:
    """The roles an account effectively holds.

    Falls back to `business_role` (then to "customer") so rows written before the
    multi-role migration, or by older code paths, still authorise correctly.
    """
    if user is None:
        return []
    roles = normalize_business_roles(getattr(user, "business_roles", None))
    if not roles:
        legacy = getattr(user, "business_role", None)
        roles = normalize_business_roles(legacy, getattr(user, "role", None))
    if not roles:
        roles = [BusinessRole.CUSTOMER.value]
    return roles


def active_role(user: User | None) -> str:
    """The role the account is currently acting as (must be one it holds)."""
    roles = resolve_roles(user)
    if not roles:
        return BusinessRole.CUSTOMER.value
    if user is not None:
        current = (getattr(user, "active_business_role", None) or "").strip().lower()
        if current in roles:
            return current
    # No valid selection recorded: prefer a workbench role so internal users do
    # not land in the customer shell after a migration.
    for role_value in roles:
        if role_value in WORKBENCH_ROLES:
            return role_value
    return roles[0]


def has_role(user: User | None, *roles: str) -> bool:
    """True when the account holds at least one of `roles` (union semantics)."""
    wanted = {str(item).strip().lower() for item in roles if item}
    if not wanted:
        return False
    return bool(wanted & set(resolve_roles(user)))


def has_any_role(user: User | None, roles: object) -> bool:
    """`has_role` for callers that already hold a set/list of role values."""
    if isinstance(roles, str):
        return has_role(user, roles)
    try:
        return has_role(user, *[str(item) for item in roles])  # type: ignore[union-attr]
    except TypeError:
        return False


def roles_contain(roles: list[str] | None, *wanted: str) -> bool:
    """Same union check for callers that already loaded the raw role column."""
    targets = {str(item).strip().lower() for item in wanted if item}
    if not targets:
        return False
    return bool(targets & set(roles or []))


def is_staff(user: User | None) -> bool:
    return bool(set(resolve_roles(user)) & STAFF_ROLES)


def is_admin(user: User | None) -> bool:
    return bool(set(resolve_roles(user)) & ADMIN_ROLES)


def has_workbench(user: User | None) -> bool:
    return bool(set(resolve_roles(user)) & WORKBENCH_ROLES)


def role_payload(user: User) -> dict:
    """Role fields shared by every user-facing response body."""
    roles = resolve_roles(user)
    return {
        "business_roles": roles,
        "active_business_role": active_role(user),
    }


def sync_legacy_business_role(user: User, roles: list[str]) -> None:
    """Keep `business_role` / `role` / `is_promotion_manager` coherent."""
    user.business_roles = list(roles)
    user.business_role = roles[0] if roles else BusinessRole.CUSTOMER.value
    user.active_business_role = active_role_from_roles(roles, user)
    user.role = required_user_role(roles)
    user.is_promotion_manager = BusinessRole.PROMOTION_MANAGER.value in roles


def grant_business_role(user: User, role_value: str) -> bool:
    """Add `role_value` to the account's role set without dropping existing ones.

    Used by store/service-area flows that used to clobber `business_role`
    (which silently removed the user's other roles under multi-role).
    Returns True when the set actually changed. Caller owns the commit.
    """
    merged = resolve_roles(user)
    normalized = normalize_business_roles(role_value)
    if not normalized:
        return False
    if normalized[0] in merged:
        return False
    merged.insert(0, normalized[0])
    sync_legacy_business_role(user, merged)
    return True


def active_role_from_roles(roles: list[str], user: User | None = None) -> str:
    """Pick the active role after an assignment change."""
    if not roles:
        return BusinessRole.CUSTOMER.value
    current = (getattr(user, "active_business_role", None) or "").strip().lower()
    if current in roles:
        return current
    for role_value in roles:
        if role_value in WORKBENCH_ROLES:
            return role_value
    return roles[0]


def role_label(role_value: str) -> str:
    """Human label used in mini-program / admin-web."""
    labels = {
        BusinessRole.CUSTOMER.value: "客户",
        BusinessRole.REPAIRER.value: "师傅",
        BusinessRole.STORE_MANAGER.value: "店长",
        BusinessRole.CITY_MANAGER.value: "城市经理",
        BusinessRole.PROMOTION_MANAGER.value: "业务",
        BusinessRole.SECOND_RECEIVER.value: "兜底",
        BusinessRole.TECH_SUPPORT.value: "技术支持",
        BusinessRole.FINANCE.value: "财务",
        BusinessRole.PLATFORM_ADMIN.value: "平台管理员",
    }
    return labels.get(role_value, role_value or "客户")


async def set_roles(
    db: AsyncSession,
    user: User,
    roles: list[str],
    *,
    operator: User | None = None,
    source: str = "admin",
    remark: str | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Replace an account's role set and record the diff.

    Returns `(roles, granted, revoked)`. Caller owns the commit.
    """
    normalized = normalize_business_roles(roles)
    if not normalized:
        raise ValueError("至少需要保留一个角色")

    before = resolve_roles(user)
    granted = [item for item in normalized if item not in before]
    revoked = [item for item in before if item not in normalized]

    operator_id = operator.id if operator is not None else None
    operator_name = operator.name if operator is not None else None
    for role_value in granted:
        db.add(
            UserRoleGrant(
                user_id=user.id,
                business_role=role_value,
                action="grant",
                operator_id=operator_id,
                operator_name=operator_name,
                source=source,
                remark=remark,
            )
        )
    for role_value in revoked:
        db.add(
            UserRoleGrant(
                user_id=user.id,
                business_role=role_value,
                action="revoke",
                operator_id=operator_id,
                operator_name=operator_name,
                source=source,
                remark=remark,
            )
        )

    sync_legacy_business_role(user, normalized)
    return normalized, granted, revoked


async def role_grants(db: AsyncSession, user_id: int, limit: int = 50) -> list[UserRoleGrant]:
    result = await db.execute(
        select(UserRoleGrant)
        .where(UserRoleGrant.user_id == user_id)
        .order_by(UserRoleGrant.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
