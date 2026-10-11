"""用户服务"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User, normalize_business_roles
from ..schemas.user import UserCreate, UserUpdate
from .role import resolve_roles, sync_legacy_business_role


async def create_user(db: AsyncSession, data: UserCreate) -> User:
    payload = data.model_dump()
    payload.pop("business_roles", None)

    # 2026-10-07 multi-role:建号即可带多个角色,留空时退回单个 business_role。
    roles = normalize_business_roles(data.business_roles or [data.business_role])
    if not roles:
        roles = normalize_business_roles(data.business_role) or ["customer"]

    user = User(**payload)
    sync_legacy_business_role(user, roles)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def get_user_by_phone(db: AsyncSession, phone: str) -> User | None:
    result = await db.execute(select(User).where(User.phone == phone))
    return result.scalar_one_or_none()


async def list_users(
    db: AsyncSession, skip: int = 0, limit: int = 20, role: str | None = None
) -> list[User]:
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    stmt = stmt.offset(skip).limit(limit).order_by(User.id.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_user(db: AsyncSession, user: User, data: UserUpdate) -> User:
    """Apply a partial update, keeping the role set coherent.

    Role字段用了「只增不减」的策略:`business_role`(老后台的单选)与
    `is_promotion_manager`(老接口的推广开关)只保证角色在集合里,不会把账号
    已有的其它角色抹掉 —— 抹角色必须显式走 `business_roles`(多选)或
    PATCH /users/{id}/roles。
    """
    payload = data.model_dump(exclude_unset=True)
    payload.pop("business_roles", None)
    for key, val in payload.items():
        setattr(user, key, val)

    if data.business_roles is not None:
        sync_legacy_business_role(user, normalize_business_roles(data.business_roles))
    else:
        merged = list(resolve_roles(user))
        changed = False
        if data.business_role is not None and data.business_role.value not in merged:
            merged.insert(0, data.business_role.value)
            changed = True
        if data.is_promotion_manager is True and "promotion_manager" not in merged:
            merged.append("promotion_manager")
            changed = True
        if changed:
            sync_legacy_business_role(user, normalize_business_roles(merged))

    await db.commit()
    await db.refresh(user)
    return user
