"""用户服务"""

from sqlalchemy import select
import secrets
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User
from ..schemas.user import UserCreate, UserUpdate


async def create_user(db: AsyncSession, data: UserCreate) -> User:
    values=data.model_dump()
    values["referral_code"] = secrets.token_urlsafe(12)
    user = User(**values)
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
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(user, key, val)
    if data.is_promotion_manager is True and data.business_role is None:
        user.business_role = "promotion_manager"
    await db.commit()
    await db.refresh(user)
    return user


async def ensure_referral_code(db: AsyncSession, user: User) -> str:
    if user.referral_code:
        return user.referral_code
    for _ in range(5):
        code=secrets.token_urlsafe(12)
        if not (await db.execute(select(User.id).where(User.referral_code == code))).scalar_one_or_none():
            user.referral_code=code
            await db.commit()
            await db.refresh(user)
            return code
    raise RuntimeError("无法生成专属推荐码")


async def bind_referrer(db: AsyncSession, user: User, code: str | None) -> None:
    if not code or user.referrer_user_id or user.promotion_manager_id or user.id is None:
        return
    inviter=(await db.execute(select(User).where(User.referral_code == code))).scalar_one_or_none()
    if not inviter or inviter.id == user.id or not inviter.is_active or inviter.is_pending_deletion:
        return
    user.referrer_user_id=inviter.id
    await db.commit()
    await db.refresh(user)
