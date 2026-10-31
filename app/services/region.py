"""区域服务 v2"""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.region import Region
from ..schemas.region import RegionCreate, RegionUpdate


async def region_references(db, region_id):
    from .. import models
    from ..models.base import Base
    labels={'regions':'下级区县','stores':'门店','orders':'订单','store_addresses':'门店地址','customer_addresses':'客户地址','repairers':'师傅档案'}
    result=[]
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if any(key.target_fullname=='regions.id' for key in column.foreign_keys):
                count=(await db.execute(select(func.count()).select_from(table).where(column==region_id))).scalar_one()
                if count: result.append(f"{labels.get(table.name, table.name)} {count} 条")
    return result


async def validate_region(db, values, region=None):
    name=''.join(str(values.get('name',region.name if region else '') or '').split())
    level=values.get('level',region.level if region else 1)
    parent_id=values.get('parent_id',region.parent_id if region else None)
    manager_id=values.get('manager_id',region.manager_id if region else None)
    if not name or level not in (1,2):raise ValueError('请填写有效名称及城市/区县层级')
    if level==1 and parent_id is not None:raise ValueError('城市无需上级区域，请清空上级')
    if level==2:
        parent=await db.get(Region,parent_id) if parent_id else None
        if not parent or parent.level!=1 or (region and parent.id==region.id):raise ValueError('区县必须选择城市作为上级')
    if manager_id is not None:
        from ..models.user import User
        if not await db.get(User,manager_id):raise ValueError('区域负责人不存在')
    structural=not region or (name,level,parent_id)!=(region.name,region.level,region.parent_id)
    if structural:
        duplicate=(await db.execute(select(Region).where(Region.name==name,Region.level==level,
            Region.parent_id==parent_id,Region.id!=(region.id if region else -1)))).scalars().first()
        if duplicate:raise ValueError('同一上级下已有同名区域，请修改已有记录，勿重复新增')
        if region:
            refs=await region_references(db,region.id)
            if refs:raise ValueError('该区域正在使用，不能变更名称或层级/上级：'+'、'.join(refs))
    return dict(name=name,level=level,parent_id=parent_id,manager_id=manager_id)


async def create_region(db: AsyncSession, data: RegionCreate) -> Region:
    r = Region(**await validate_region(db,data.model_dump()))
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


async def update_region(db: AsyncSession, region: Region, data: RegionUpdate) -> Region:
    values=await validate_region(db,data.model_dump(exclude_unset=True),region)
    for key,val in values.items():setattr(region,key,val)
    await db.commit()
    await db.refresh(region)
    return region


async def delete_region(db: AsyncSession, region: Region):
    refs=await region_references(db,region.id)
    if refs:raise ValueError('该区域仍有关联，不能删除：'+'、'.join(refs)+'；请先调整关联')
    await db.delete(region)
    await db.commit()
