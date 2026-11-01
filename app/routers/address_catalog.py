"""Administrative catalog is the only address authoring entry point."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.auth import require_roles
from ..core.database import get_db
from ..models.store import StoreAddress, Store
from ..schemas.store import StoreAddressOut
from ..services import address_catalog as service

router=APIRouter(prefix='/api/v1/address-catalog',tags=['城市区域地址库'])
admin=Depends(require_roles('platform_admin'))


class Entry(BaseModel):
    region_id:int
    estate:str=Field(min_length=1,max_length=120)
    building:str=Field(default='',max_length=80)
    unit:str=Field(default='',max_length=80)
    room:str=Field(default='',max_length=80)
    door_number:str=Field(default='',max_length=240)
    aliases:str=Field(default='',max_length=4000)
    detail_hint:str=Field(default='',max_length=300)
    source_name:str=Field(default='',max_length=80)
    source_ref:str=Field(default='',max_length=240)
    enabled:bool=True


class ImportEntries(BaseModel):
    items:list[Entry]=Field(min_length=1,max_length=2000)


class Scope(BaseModel):
    service_area_id:int
    building:str|None=Field(default=None,max_length=80)
    address_id:int|None=None


class Scopes(BaseModel):
    items:list[Scope]=Field(default_factory=list,max_length=2000)


@router.get('',response_model=list[StoreAddressOut])
async def entries(db:AsyncSession=Depends(get_db),user=admin):
    return (await db.execute(select(StoreAddress).order_by(StoreAddress.id.desc()))).scalars().all()


@router.post('',response_model=StoreAddressOut)
async def create(data:Entry,db:AsyncSession=Depends(get_db),user=admin):
    try:
        row=await service.save_entry(db,data,user.id)
        await db.commit()
        return row
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(400,str(exc))


@router.post('/import')
async def import_entries(data:ImportEntries,db:AsyncSession=Depends(get_db),user=admin):
    ids=[]
    try:
        for i,item in enumerate(data.items):
            # An import uses the same validation as manual creation; all-or-nothing.
            row=await service.save_entry(db,item,user.id)
            ids.append(row.id)
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(400,f'第{i+1}行：{exc}')
    return dict(imported=len(ids),ids=ids)


@router.put('/{address_id}',response_model=StoreAddressOut)
async def update(address_id:int,data:Entry,db:AsyncSession=Depends(get_db),user=admin):
    row=await db.get(StoreAddress,address_id)
    if not row: raise HTTPException(404,'地址不存在')
    try:
        await service.save_entry(db,data,user.id,row)
        await db.commit()
        return row
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(400,str(exc))


@router.delete('/{address_id}')
async def remove(address_id:int,db:AsyncSession=Depends(get_db),user=admin):
    row=await db.get(StoreAddress,address_id)
    if not row: raise HTTPException(404,'地址不存在')
    row.enabled=False
    await db.commit()
    return dict(deleted=True)


@router.get('/coverage/{store_id}')
async def coverage(store_id:int,db:AsyncSession=Depends(get_db),user=admin):
    return await service.coverage(db,store_id)


@router.put('/coverage/{store_id}')
async def save_coverage(store_id:int,data:Scopes,db:AsyncSession=Depends(get_db),user=admin):
    store=await db.get(Store,store_id)
    if not store: raise HTTPException(404,'门店不存在')
    try: return await service.save_coverage(db,store,data.items,user.id)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(400,str(exc))
