"""Single catalog and hierarchical, non-overlapping store coverage."""
import hashlib
from sqlalchemy import select, delete, update
from ..models.store import AddressCoverage, StoreAddress, Store, StoreStatus
from ..models.service_area import ServiceArea
from ..models.region import Region
from .address_format import clean, door_number, full_address


async def estate_area(db, region_id, estate):
    from .store import district_region
    city, district = await district_region(db, region_id)
    name = clean(estate)
    if not name:
        raise ValueError('请填写小区名称')
    code = 'ESTATE-' + hashlib.sha256(f'{city.name}|{district.name}|{name}'.encode()).hexdigest()[:24]
    area = (await db.execute(select(ServiceArea).where(ServiceArea.code == code))).scalar_one_or_none()
    if not area:
        area = ServiceArea(code=code, province='', city=city.name, district=district.name,
            street='', name=name, area_type='estate', source_name='城市区域地址库',
            source_url='', source_published_at='', active=True)
        db.add(area)
        await db.flush()
    return area


async def save_entry(db, data, operator_id, address=None):
    from .store import _address_identity
    area = await estate_area(db, data.region_id, data.estate)
    if data.entrance_type not in ['普通单元','道路门牌','待确认']:raise ValueError('入口类型不正确')
    if data.entrance_type=='待确认' and not data.review_required:raise ValueError('请先核实并修改入口类型，再允许开放地址')
    road=clean(data.road_number) if data.entrance_type=='道路门牌' else ''
    if road and road[-1:].isdigit():road+='号'
    entrance=road or clean(data.entrance_name or data.unit)
    door = door_number(data.door_number, data.building, data.unit, data.room)
    if data.property_type=='车位' and not clean(data.door_number):
        door=clean(data.building)+clean(data.unit)+clean(data.room)+('' if clean(data.room).endswith('位') else '车位')
    if data.entrance_type=='道路门牌':
        if not road or not clean(data.room):raise ValueError('道路门牌类型必须填写道路门牌和房号')
        door=road+clean(data.room)+('' if clean(data.room).endswith(('室','号','铺','房','位')) else ('车位' if data.property_type=='车位' else '室'))
    if not door:
        raise ValueError('请填写门牌号，或楼栋及房号')
    _, key, code = _address_identity([area.city, area.district, area.name, door])
    rows = (await db.execute(select(StoreAddress).where(StoreAddress.service_area_id == area.id))).scalars().all()
    if any(r.id != (address.id if address else None) and (r.canonical_key == key or
            (clean(data.building) and clean(data.room) and (r.building,r.entrance_name or r.unit,r.room) ==
             (clean(data.building),entrance,clean(data.room)))) for r in rows):
        raise ValueError('该实体地址已存在，请修改原地址或添加同址别名')
    if address and (address.service_area_id != area.id or address.building != clean(data.building) or (address.entrance_name or address.unit)!=entrance):
        rules = (await db.execute(select(AddressCoverage).where(AddressCoverage.address_id == address.id))).scalars().all()
        if rules:
            raise ValueError('请先从门店服务范围移除此门牌，再调整其小区或楼栋')
    if address is None:
        address = StoreAddress(created_by_user_id=operator_id, store_id=None)
        db.add(address)
    for k,v in dict(region_id=data.region_id,service_area_id=area.id,province=area.province,
            city=area.city,district=area.district,street='',community=area.name,estate=area.name,
            building=clean(data.building),unit=clean(data.unit),room=clean(data.room),door_number=door,
            canonical_key=key,address_code=code,full_address=(clean(area.city)+clean(area.district)+door if data.entrance_type=='道路门牌' else full_address(area.city,area.district,area.name,door)),
            entrance_type=data.entrance_type,entrance_name=entrance,road_number=road,review_required=data.review_required,property_type=data.property_type,
            aliases=data.aliases,detail_hint=data.detail_hint,source_name=data.source_name,
            source_ref=data.source_ref,catalog_published=True,enabled=data.enabled).items():
        setattr(address,k,v)
    await db.flush()
    return address


def matches(rule, address):
    return rule.service_area_id == address.service_area_id and (rule.property_type is None or rule.property_type==address.property_type) and (rule.address_id == address.id if rule.address_id
        else (rule.building is None or rule.building==address.building) and (rule.entrance_name is None or rule.entrance_name==(address.entrance_name or address.unit)))


async def resolve_address(db, address):
    area = await db.get(ServiceArea,address.service_area_id) if address else None
    if not address or not address.enabled or address.review_required or not address.catalog_published or not area or not area.active:
        raise ValueError('请选择城市区域地址库中的有效地址')
    rules = (await db.execute(select(AddressCoverage).where(AddressCoverage.service_area_id == area.id))).scalars().all()
    owners = {r.store_id for r in rules if matches(r,address)}
    if len(owners) != 1:
        raise ValueError('该地址尚未分配服务门店，请联系平台')
    store = await db.get(Store,next(iter(owners)))
    if not store or not store.enabled or store.status != StoreStatus.ACTIVE:
        raise ValueError('该地址的服务门店暂未开通')
    return area, None, store


async def coverage(db, store_id):
    rules = (await db.execute(select(AddressCoverage).where(AddressCoverage.store_id == store_id))).scalars().all()
    return [dict(service_area_id=r.service_area_id,building=r.building,entrance_name=r.entrance_name,property_type=r.property_type,address_id=r.address_id) for r in rules]


async def save_coverage(db, store, items, operator_id):
    from .store import district_region
    # Take the district write lock before reading competing stores' rules.
    # SQLite serializes writers; row-locking databases serialize this district.
    await db.execute(update(Region).where(Region.id==store.region_id).values(name=Region.name))
    city,district = await district_region(db,store.region_id)
    if items and (not store.enabled or store.status != StoreStatus.ACTIVE):
        raise ValueError('请先启用并开通门店')
    desired=[]
    all_rules=(await db.execute(select(AddressCoverage))).scalars().all()
    for item in items:
        area=await db.get(ServiceArea,item.service_area_id)
        if not area or not area.active or area.area_type != 'estate' or (area.city,area.district)!=(city.name,district.name):
            raise ValueError('只能分配本门店所属区县的有效地址库小区')
        kind=item.property_type
        if kind is not None:
            available=(await db.execute(select(StoreAddress.id).where(StoreAddress.service_area_id==area.id,StoreAddress.property_type==kind,StoreAddress.enabled==True))).first()
            if not available:raise ValueError('该小区尚无此类有效地址，不能分配空类别')
        address=await db.get(StoreAddress,item.address_id) if item.address_id else None
        if item.address_id and (not address or not address.enabled or address.review_required or address.service_area_id != area.id):
            raise ValueError('门牌不存在或不属于所选小区')
        building=clean(item.building) if item.building is not None else None
        entrance=clean(item.entrance_name) if item.entrance_name is not None else None
        if entrance is not None and building is None:raise ValueError('分配入口时必须同时选择楼栋')
        if address:
            if kind is not None and kind!=address.property_type:raise ValueError('地址类型与服务范围不一致')
            building=None;entrance=None
        if building is not None:
            found=(await db.execute(select(StoreAddress.id).where(StoreAddress.service_area_id==area.id,
                StoreAddress.building==building,StoreAddress.enabled==True,StoreAddress.property_type==kind if kind else True))).first()
            if not found: raise ValueError('楼栋不在城市区域地址库中')
            if entrance is not None:
                found=(await db.execute(select(StoreAddress).where(StoreAddress.service_area_id==area.id,StoreAddress.building==building,StoreAddress.enabled==True,StoreAddress.property_type==kind if kind else True))).scalars().all()
                if not any((r.entrance_name or r.unit)==entrance for r in found):raise ValueError('入口不在城市区域地址库中')
        rule=AddressCoverage(store_id=store.id,service_area_id=area.id,building=building,
            entrance_name=entrance,property_type=kind,address_id=address.id if address else None,operator_id=operator_id)
        for other in all_rules:
            if other.store_id == store.id or other.service_area_id != area.id: continue
            if other.property_type is not None and kind is not None and other.property_type!=kind:continue
            overlap=False
            if other.address_id:
                target=await db.get(StoreAddress,other.address_id)
                overlap=bool(target and matches(rule,target))
            elif rule.address_id:
                overlap=matches(other,address)
            else:
                overlap=(other.building is None or building is None or other.building==building) and (other.entrance_name is None or entrance is None or other.entrance_name==entrance)
            if overlap: raise ValueError(f'{area.name}的服务范围与其他门店重叠，请先从原门店移除')
        identity=(rule.service_area_id,rule.building,rule.entrance_name,rule.property_type,rule.address_id)
        if identity not in {(r.service_area_id,r.building,r.entrance_name,r.property_type,r.address_id) for r in desired}: desired.append(rule)
    await db.execute(delete(AddressCoverage).where(AddressCoverage.store_id==store.id))
    db.add_all(desired)
    await db.commit()
    return await coverage(db,store.id)


async def public_catalog(db):
    areas=(await db.execute(select(ServiceArea).where(ServiceArea.active==True,ServiceArea.area_type=='estate'))).scalars().all()
    rows=(await db.execute(select(StoreAddress).where(StoreAddress.enabled==True,StoreAddress.catalog_published==True,StoreAddress.review_required==False))).scalars().all()
    rules=(await db.execute(select(AddressCoverage))).scalars().all()
    stores={s.id:s for s in (await db.execute(select(Store))).scalars().all()}
    result=[]
    for area in areas:
        addresses=[]
        for row in rows:
            if row.service_area_id!=area.id: continue
            owners={r.store_id for r in rules if matches(r,row)}
            if len(owners)!=1: continue
            store=stores.get(next(iter(owners)))
            if not store or not store.enabled or store.status!=StoreStatus.ACTIVE: continue
            addresses.append(dict(id=row.id,estate=row.estate,building=row.building,unit=row.entrance_name or row.unit,room=row.room,
                door_number=row.door_number or '',aliases=row.aliases or '',search_aliases=row.search_aliases or '',
                entrance_name=row.entrance_name or row.unit,entrance_type=row.entrance_type,road_number=row.road_number,full_address=row.full_address,store_id=store.id,
                store_name=store.name,region_id=store.region_id))
        if addresses:
            result.append(dict(id=area.id,service_area_id=area.id,name=area.name,city=area.city,
                district=area.district,street='',community_code=area.community_code,estate_aliases=area.estate_aliases,estates=[area.name],addresses=addresses))
    return result
