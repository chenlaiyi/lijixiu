"""Saved address selection and catalog edits preserve historical order snapshots."""
import asyncio,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DATABASE_URL']='sqlite+aiosqlite:///:memory:'
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.models.base import Base
from app.models import User,UserRole,Region,Store,StoreStatus
from app.routers.address_catalog import Entry,Scope,remove
from app.services.address_catalog import save_entry,save_coverage,public_catalog
from app.services.business import create_address,update_address,list_addresses
from app.services.order import create_order
from app.schemas.business import AddressCreate,AddressUpdate
from app.schemas.order import OrderCreate

async def main():
 engine=create_async_engine('sqlite+aiosqlite:///:memory:')
 async with engine.begin() as c:await c.run_sync(Base.metadata.create_all)
 async with async_sessionmaker(engine,expire_on_commit=False)() as db:
  user=User(name='customer',phone='19900000001',role=UserRole.CUSTOMER)
  admin=User(name='admin',phone='19900000002',role=UserRole.ADMIN,business_role='platform_admin')
  city=Region(name='厦门市',level=1);db.add_all([user,admin,city]);await db.flush()
  county=Region(name='海沧区',level=2,parent_id=city.id);db.add(county);await db.flush()
  store=Store(name='服务店',region_id=county.id,manager_id=admin.id,status=StoreStatus.ACTIVE,enabled=True)
  db.add(store);await db.commit()
  entry=Entry(region_id=county.id,estate='蓝月湾一期',building='S5栋',room='2605',door_number='嵩屿北五里27号2605室',aliases='蓝月湾一期S5栋2605室',detail_hint='内部核验')
  leaf=await save_entry(db,entry,admin.id);await db.commit()
  await save_coverage(db,store,[Scope(service_area_id=leaf.service_area_id)],admin.id)
  saved=await create_address(db,AddressCreate(user_id=user.id,service_address_id=leaf.id,contact_name='C',contact_phone='19900000001'))
  args=dict(customer_id=user.id,region_id=county.id,address_book_id=leaf.id,address='spoofed',description='repair')
  order=await create_order(db,OrderCreate(**args));snapshot=order.address
  assert order.address_book_id==leaf.id and order.address==leaf.full_address
  edited=entry.model_copy(update={'door_number':'嵩屿北五里27号2605室(东门)','aliases':'蓝月湾一期S5栋2605室；东门2605'})
  await save_entry(db,edited,admin.id,leaf);await db.commit()
  assert order.address==snapshot
  assert (await list_addresses(db,user.id))[0].address==leaf.full_address
  await update_address(db,saved,AddressUpdate(service_address_id=leaf.id,contact_name='新联系人'))
  assert saved.service_address_id==leaf.id and saved.contact_name=='新联系人'
  catalog=await public_catalog(db)
  assert catalog[0]['addresses'][0]['id']==leaf.id
  assert '内部核验' not in str(catalog)
  order.estate='仅历史订单出现';await db.commit()
  assert catalog[0]['estates']==['蓝月湾一期']
  await remove(leaf.id,db,admin)
  assert await public_catalog(db)==[]
  try:await create_order(db,OrderCreate(**args));raise AssertionError('Deleted address accepted')
  except ValueError:pass
  assert order.address==snapshot
  print('PASS saved-address IDs, catalog edits, internal notes, no order-derived addresses, deletion and immutable snapshots')
 await engine.dispose()

if __name__=='__main__':asyncio.run(main())
