"""Administrative catalog is the only address authoring entry point."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
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
    entrance_type:str=Field(default='普通单元',max_length=30)
    entrance_name:str=Field(default='',max_length=160)
    road_number:str=Field(default='',max_length=160)
    review_required:bool=False
    enabled:bool=True


class ImportEntries(BaseModel):
    items:list[Entry]=Field(min_length=1,max_length=2000)


class Scope(BaseModel):
    service_area_id:int
    building:str|None=Field(default=None,max_length=80)
    entrance_name:str|None=Field(default=None,max_length=160)
    address_id:int|None=None


class Scopes(BaseModel):
    items:list[Scope]=Field(default_factory=list,max_length=2000)


@router.get('/template.csv')
async def download_template(user=admin):
    from ..services.catalog_files import template_csv
    return Response(template_csv(),media_type='text/csv; charset=utf-8',headers={
        'Content-Disposition':'attachment; filename="address-catalog-template.csv"'})


@router.post('/import-file')
async def import_file(file:UploadFile=File(...),apply:bool=Form(False),expected_hash:str=Form(''),
        db:AsyncSession=Depends(get_db),user=admin):
    from ..services.catalog_import import make_plan,apply_plan
    content=await file.read(15*1024*1024+1)
    try:
        if apply:
            return await apply_plan(db,file.filename or '',content,user.id,expected_hash)
        report,_=await make_plan(db,file.filename or '',content)
        return report
    except (ValueError,UnicodeError,KeyError) as exc:
        await db.rollback()
        raise HTTPException(400,str(exc))
    except Exception:
        await db.rollback()
        raise


@router.get('',response_model=list[StoreAddressOut])
async def entries(db:AsyncSession=Depends(get_db),user=admin):
    from ..models.service_area import ServiceArea
    rows=(await db.execute(select(StoreAddress).order_by(StoreAddress.id.desc()))).scalars().all()
    areas={a.id:a for a in (await db.execute(select(ServiceArea))).scalars().all()}
    for row in rows:
        area=areas.get(row.service_area_id)
        row.community_code=area.community_code if area else None
    return rows


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
