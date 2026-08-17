"""区域服务 v2"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.region import Region
from ..schemas.region import RegionCreate, RegionUpdate


async def create_region(db: AsyncSession, data: RegionCreate) -> Region:
    r = Region(**data.model_dump())
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


async def get_region(db: AsyncSession, region_id: int) -> Region | None:
    return await db.get(Region, region_id)


async def list_regions(
    db: AsyncSession, parent_id: int | None = None, level: int | None = None
) -> list[Region]:
    stmt = select(Region)
    if parent_id is not None:
        stmt = stmt.where(Region.parent_id == parent_id)
    if level is not None:
        stmt = stmt.where(Region.level == level)
    stmt = stmt.order_by(Region.id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_region_tree(db: AsyncSession) -> list[dict]:
    """返回省→市→区的树形结构"""
    all_regions = (await db.execute(
        select(Region).order_by(Region.level, Region.id)
    )).scalars().all()

    region_map = {}
    for r in all_regions:
        region_map[r.id] = {"id": r.id, "name": r.name, "level": r.level, "children": []}

    tree = []
    for r in all_regions:
        node = region_map[r.id]
        if r.parent_id and r.parent_id in region_map:
            region_map[r.parent_id]["children"].append(node)
        else:
            tree.append(node)

    return tree


async def update_region(
    db: AsyncSession, region: Region, data: RegionUpdate
) -> Region:
    """更新区域信息（如设置负责人）"""
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(region, key, val)
    await db.commit()
    await db.refresh(region)
    return region
