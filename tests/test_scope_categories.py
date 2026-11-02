import asyncio,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));os.environ['DATABASE_URL']='sqlite+aiosqlite:///:memory:'
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.models.base import Base
from app.models import User,UserRole,Region,Store,StoreStatus
from app.services.address_catalog import save_entry,save_coverage,resolve_address,public_catalog
from app.routers.address_catalog import Entry,Scope
async def main():
 engine=create_async_engine('sqlite+aiosqlite:///:memory:')
 async with engine.begin() as c:await c.run_sync(Base.metadata.create_all)
 async with async_sessionmaker(engine,expire_on_commit=False)() as db:
  admin=User(name='admin',phone='19900000001',role=UserRole.ADMIN,business_role='platform_admin');city=Region(name='厦门市',level=1);db.add_all([admin,city]);await db.flush()
  county=Region(name='海沧区',level=2,parent_id=city.id);db.add(county);await db.flush()
  stores=[Store(name=name,region_id=county.id,manager_id=admin.id,status=StoreStatus.ACTIVE,enabled=True) for name in ['住宅店','商业店']];db.add_all(stores);await db.commit()
  rows=[]
  for kind,building in [('住宅','S6号楼'),('商业','商业楼'),('车位','车库')]:
   row=await save_entry(db,Entry(region_id=county.id,estate='蓝月湾一期',property_type=kind,building=building,unit='1单元',room='101'),admin.id);rows.append(row)
  await db.commit();area=rows[0].service_area_id
  assert rows[2].full_address.endswith('101车位')
  await save_coverage(db,stores[0],[Scope(service_area_id=area,property_type='住宅')],admin.id)
  assert (await resolve_address(db,rows[0]))[2].id==stores[0].id
  for row in rows[1:]:
   try:await resolve_address(db,row);raise AssertionError('unselected category opened')
   except ValueError:pass
  await save_coverage(db,stores[1],[Scope(service_area_id=area,property_type='商业')],admin.id)
  assert (await resolve_address(db,rows[1]))[2].id==stores[1].id
  future=await save_entry(db,Entry(region_id=county.id,estate='蓝月湾一期',property_type='住宅',building='S7号楼',room='202'),admin.id);await db.commit()
  assert (await resolve_address(db,future))[2].id==stores[0].id
  assert len((await public_catalog(db))[0]['addresses'])==3
  try:await save_coverage(db,stores[0],[Scope(service_area_id=area)],admin.id);raise AssertionError('broad cross-category overlap accepted')
  except ValueError:pass
  try:await save_coverage(db,stores[0],[Scope(service_area_id=area,property_type='住宅',building='商业楼')],admin.id);raise AssertionError('wrong category building accepted')
  except ValueError:pass
  from app.routers.address_catalog import update as update_entry
  from app.schemas.store import StoreAddressOut
  edited=await update_entry(rows[0].id,Entry(region_id=county.id,estate='蓝月湾一期',property_type='住宅',building='S6号楼',unit='1单元',room='101',detail_hint='修改后返回序列化'),db,admin)
  assert StoreAddressOut.model_validate(edited).updated_at is not None
  print('PASS typed category coverage, commercial/residential separation, parking opt-in, future residential inheritance and overlap validation')
 await engine.dispose()
asyncio.run(main())
