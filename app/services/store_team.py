"""City-scoped, multi-store technician membership."""
from sqlalchemy import select
from ..models.store import Store, StoreStaff, StoreStaffRole
from ..models.repairer import Repairer
from ..models.region import Region

async def city_id(db, region_id):
    seen=set()
    while region_id and region_id not in seen:
        seen.add(region_id)
        region=await db.get(Region, region_id)
        if not region:return None
        if region.level==1:return region.id
        region_id=region.parent_id
    return None

async def validate_member(db, store_id, repairer_id):
    store=await db.get(Store,store_id);r=await db.get(Repairer,repairer_id)
    if not store or not r:raise ValueError('门店或师傅不存在')
    if not r.region_id or await city_id(db,r.region_id)!=await city_id(db,store.region_id):
        raise ValueError('请先设置师傅所属城市，且必须与门店同市')
    member=(await db.execute(select(StoreStaff).where(StoreStaff.store_id==store_id,StoreStaff.repairer_id==repairer_id,StoreStaff.active==True,StoreStaff.role.in_([StoreStaffRole.TECHNICIAN,StoreStaffRole.SECOND_RECEIVER])))).scalars().first()
    if not member and store.default_second_receiver_id!=repairer_id:
        raise ValueError('请先将师傅添加到本门店')

async def team(db, store):
    members=(await db.execute(select(StoreStaff).where(StoreStaff.store_id==store.id,StoreStaff.active==True,StoreStaff.role.in_([StoreStaffRole.TECHNICIAN,StoreStaffRole.SECOND_RECEIVER])))).scalars().all()
    ids={m.repairer_id for m in members if m.repairer_id}
    if store.default_second_receiver_id:ids.add(store.default_second_receiver_id)
    rows=(await db.execute(select(Repairer).where(Repairer.id.in_(ids)))).scalars().all()
    city=await city_id(db,store.region_id)
    return [r for r in rows if await city_id(db,r.region_id)==city]
