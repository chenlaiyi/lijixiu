"""师傅服务"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.repairer import Repairer
from ..schemas.repairer import RepairerCreate, RepairerUpdate


async def create_repairer(db: AsyncSession, data: RepairerCreate) -> Repairer:
    r = Repairer(**data.model_dump())
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


async def get_repairer(db: AsyncSession, repairer_id: int) -> Repairer | None:
    return await db.get(Repairer, repairer_id)


async def get_repairer_by_user(db: AsyncSession, user_id: int) -> Repairer | None:
    result = await db.execute(
        select(Repairer).where(Repairer.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def list_repairers(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    region_id: int | None = None,
    status: str | None = None,
) -> list[Repairer]:
    stmt = select(Repairer)
    if region_id:
        stmt = stmt.where(Repairer.region_id == region_id)
    if status:
        stmt = stmt.where(Repairer.status == status)
    stmt = stmt.offset(skip).limit(limit).order_by(Repairer.rating.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_repairer(
    db: AsyncSession, repairer: Repairer, data: RepairerUpdate
) -> Repairer:
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(repairer, key, val)
    await db.commit()
    await db.refresh(repairer)
    return repairer


async def ensure_role_profiles(db: AsyncSession, user=None):
    """Provision only missing repairer profiles, never fabricate qualifications."""
    from ..models.user import User
    users = [user] if user else (await db.execute(select(User))).scalars().all()
    count = 0
    for item in users:
        if not item.is_active or 'repairer' not in item.business_roles:
            continue
        if await get_repairer_by_user(db, item.id):
            continue
        db.add(Repairer(user_id=item.id, skills='待完善', status='offline',
            intro='请完善技能和服务区域后再接单'))
        await db.flush()
        count += 1
    return count
