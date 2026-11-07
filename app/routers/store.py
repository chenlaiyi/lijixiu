"""Store, staff, address-book, and unopened-area routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user, require_staff, require_admin, require_roles
from ..core.database import get_db
from ..models.user import User
from ..schemas.store import (
    AreaOpenRequestCreate,
    AreaOpenRequestOut,
    StoreAddressCreate,
    StoreAddressOut,
    StoreAddressUpdate,
    StoreCreate,
    StoreOut,
    StoreStaffCreate,
    StoreStaffOut,
    StoreUpdate,
    StoreCoverageUpdate,
)
from ..services import store as store_service

router = APIRouter(prefix="/api/v1/stores", tags=["stores"])


@router.post("", response_model=StoreOut, status_code=201)
async def create_store(
    data: StoreCreate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_admin),
):
    try:
        return await store_service.create_store(db, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("", response_model=list[StoreOut])
async def list_stores(
    region_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await store_service.list_stores(db, region_id)


@router.patch("/{store_id}", response_model=StoreOut)
async def update_store(
    store_id: int,
    data: StoreUpdate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_roles("platform_admin", "store_manager")),
):
    store = await store_service.get_store(db, store_id)
    if not store:
        raise HTTPException(404, "Store not found")
    if 'platform_admin' not in _staff.business_roles and store.manager_id != _staff.id:
        raise HTTPException(403, "只能修改本人负责的门店")
    try:
        return await store_service.update_store(db, store, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/{store_id}/staff", response_model=StoreStaffOut, status_code=201)
async def add_staff(
    store_id: int,
    data: StoreStaffCreate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_roles("platform_admin", "store_manager")),
):
    store = await store_service.get_store(db, store_id)
    if not store:
        raise HTTPException(404, "Store not found")
    if 'platform_admin' not in _staff.business_roles and store.manager_id!=_staff.id:raise HTTPException(403,'只能管理本人门店')
    if data.repairer_id:
        from ..services.store_team import city_id
        from ..models.repairer import Repairer
        r=await db.get(Repairer,data.repairer_id)
        if not r or r.user_id!=data.user_id or await city_id(db,r.region_id)!=await city_id(db,store.region_id):raise HTTPException(400,'师傅账号或所属城市不匹配')
    return await store_service.add_store_staff(db, store_id, data)


@router.get("/{store_id}/staff", response_model=list[StoreStaffOut])
async def list_staff(
    store_id: int,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
):
    return await store_service.list_store_staff(db, store_id)


async def _check_address_scope(db, user, service_area_id):
    if 'platform_admin' in user.business_roles:
        return
    from ..services.service_area import resolve_open_area
    try:
        _, _, store = await resolve_open_area(db, service_area_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if store.manager_id != user.id:
        raise HTTPException(403, "只能维护本人负责门店的地址")


@router.post("/addresses", response_model=StoreAddressOut, status_code=201)
async def create_address(
    data: StoreAddressCreate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_roles("platform_admin", "store_manager")),
):
    raise HTTPException(400, "请在城市区域地址库创建地址")


@router.get("/addresses", response_model=list[StoreAddressOut])
async def list_addresses(
    store_id: int | None = None,
    region_id: int | None = None,
    service_area_id: int | None = None,
    enabled: bool | None = None,
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await store_service.list_addresses(
        db, store_id, region_id, service_area_id, enabled, q
    )


@router.patch("/addresses/{address_id}", response_model=StoreAddressOut)
async def update_address(
    address_id: int,
    data: StoreAddressUpdate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_roles("platform_admin", "store_manager")),
):
    raise HTTPException(400, "请在城市区域地址库修改地址")


@router.post("/area-open-requests", response_model=AreaOpenRequestOut, status_code=201)
async def create_area_open_request(
    data: AreaOpenRequestCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await store_service.create_area_open_request(db, data)


@router.delete("/addresses/{address_id}")
async def delete_address(address_id: int, db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_roles("platform_admin"))):
    raise HTTPException(400, "请在城市区域地址库修改地址")


@router.get("/{store_id}/coverage")
async def get_store_coverage(store_id:int, db:AsyncSession=Depends(get_db), admin:User=Depends(require_roles('platform_admin'))):
    store = await store_service.get_store(db,store_id)
    if not store: raise HTTPException(404,"门店不存在")
    return await store_service.store_coverage(db,store)


@router.put("/{store_id}/coverage")
async def put_store_coverage(store_id:int,data:StoreCoverageUpdate,db:AsyncSession=Depends(get_db),admin:User=Depends(require_roles('platform_admin'))):
    raise HTTPException(400, '请从城市区域地址库分配门店服务地址范围')


class TeamUpdate(__import__('pydantic').BaseModel):
    repairer_ids: list[int]

async def _team_store(db, store_id, user):
    store=await store_service.get_store(db,store_id)
    if not store:raise HTTPException(404,'门店不存在')
    if 'platform_admin' not in user.business_roles and store.manager_id!=user.id:
        raise HTTPException(403,'只能管理本人门店师傅')
    return store

@router.get('/{store_id}/technicians')
async def technicians(store_id:int,db:AsyncSession=Depends(get_db),user:User=Depends(require_roles('platform_admin','store_manager'))):
    from ..services.store_team import team
    from ..schemas.repairer import RepairerOut
    store=await _team_store(db,store_id,user)
    result=[]
    for r in await team(db,store):
        account=await db.get(User,r.user_id)
        result.append({**RepairerOut.model_validate(r).model_dump(),'display_name':account.name if account else '师傅'})
    return result

@router.put('/{store_id}/technicians')
async def save_technicians(store_id:int,data:TeamUpdate,db:AsyncSession=Depends(get_db),user:User=Depends(require_roles('platform_admin','store_manager'))):
    from sqlalchemy import select
    from ..models.store import StoreStaff,StoreStaffRole
    from ..models.repairer import Repairer
    from ..services.store_team import city_id
    store=await _team_store(db,store_id,user)
    city=await city_id(db,store.region_id)
    selected=[]
    for rid in set(data.repairer_ids):
        r=await db.get(Repairer,rid)
        if not r or not r.region_id or await city_id(db,r.region_id)!=city:raise HTTPException(400,'只能添加与门店同市的师傅，请先完善城市')
        selected.append(r)
    members=(await db.execute(select(StoreStaff).where(StoreStaff.store_id==store_id,StoreStaff.role==StoreStaffRole.TECHNICIAN))).scalars().all()
    for m in members:m.active=m.repairer_id in data.repairer_ids
    for r in selected:
        if not any(m.repairer_id==r.id for m in members):db.add(StoreStaff(store_id=store_id,user_id=r.user_id,repairer_id=r.id,role=StoreStaffRole.TECHNICIAN,active=True))
    store.default_second_receiver_id=None
    await db.commit()
    return {'saved':len(selected)}


@router.get('/order-alerts/pending')
async def order_alerts(db:AsyncSession=Depends(get_db),user:User=Depends(require_roles('platform_admin','store_manager'))):
    from sqlalchemy import select
    from ..models.order import Order,OrderStatus
    from ..models.store import Store
    rows=(await db.execute(select(Order.id,Order.store_id,Order.status).join(Store,Store.id==Order.store_id).where(Store.manager_id==user.id,Order.status.in_([OrderStatus.STORE_PENDING,OrderStatus.PAID_PENDING_REVIEW])).order_by(Order.id.desc()).limit(100))).all()
    return [{'id':r.id,'store_id':r.store_id,'status':r.status.value} for r in rows]


@router.get('/{store_id}/technician-candidates')
async def technician_candidates(store_id:int,db:AsyncSession=Depends(get_db),user:User=Depends(require_roles('platform_admin','store_manager'))):
    from sqlalchemy import select
    from ..models.repairer import Repairer
    from ..services.store_team import city_id
    from ..schemas.repairer import RepairerOut
    store=await _team_store(db,store_id,user);city=await city_id(db,store.region_id)
    rows=(await db.execute(select(Repairer))).scalars().all();result=[]
    for r in rows:
        account=await db.get(User,r.user_id)
        if account and account.is_active and await city_id(db,r.region_id)==city:
            result.append({**RepairerOut.model_validate(r).model_dump(),'display_name':account.name})
    return result
