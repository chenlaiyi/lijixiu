"""Catalog-before-store, hierarchical coverage, immutable orders and atomic imports."""
import asyncio
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DATABASE_URL']='sqlite+aiosqlite:///:memory:'
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.models.base import Base
from app.models import User,UserRole,Region,Store,StoreStatus,StoreAddress
from app.routers.address_catalog import Entry,Scope,ImportEntries,import_entries
from app.schemas.order import OrderCreate
from app.schemas.business import AddressCreate,DomesticDemandCreate
from app.schemas.store import StoreUpdate
from app.services import address_catalog as catalog
from app.services.order import create_order
from app.services.store import update_store
from app.services.business import create_address,create_demand
from fastapi import HTTPException


async def rejects(call):
    try: await call
    except (ValueError,HTTPException): return
    raise AssertionError('Expected rejected operation')


async def main():
    engine=create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as c:await c.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine,expire_on_commit=False)() as db:
        admin=User(name='admin',phone='19900000001',role=UserRole.ADMIN,business_role='platform_admin')
        customer=User(name='customer',phone='19900000002',role=UserRole.CUSTOMER)
        city=Region(name='厦门市',level=1)
        db.add_all([admin,customer,city]);await db.flush()
        county=Region(name='海沧区',level=2,parent_id=city.id)
        db.add(county);await db.commit()
        entry=lambda room,building='S5栋':Entry(region_id=county.id,estate='蓝月湾一期',building=building,
            unit='1单元',room=room,aliases='厦门市海沧区嵩屿北五里27号'+room+'室',detail_hint='内部备注')
        address=await catalog.save_entry(db,entry('2605'),admin.id)
        await db.commit()
        assert address.store_id is None and not await catalog.public_catalog(db)
        await rejects(catalog.save_entry(db,entry('2605'),admin.id))
        stores=[Store(name=n,region_id=county.id,manager_id=admin.id,status=StoreStatus.ACTIVE,enabled=True) for n in ['店A','店B']]
        db.add_all(stores);await db.commit()
        area_id=address.service_area_id
        await catalog.save_coverage(db,stores[0],[Scope(service_area_id=area_id,building='S5栋')],admin.id)
        second=await catalog.save_entry(db,entry('2606'),admin.id)
        other=await catalog.save_entry(db,entry('2605','S6栋'),admin.id)
        await db.commit()
        assert (await catalog.resolve_address(db,second))[2].id==stores[0].id
        await rejects(catalog.resolve_address(db,other))
        await rejects(catalog.save_coverage(db,stores[1],[Scope(service_area_id=area_id)],admin.id))
        assert not await catalog.coverage(db,stores[1].id)
        await catalog.save_coverage(db,stores[1],[Scope(service_area_id=area_id,address_id=other.id)],admin.id)
        public=await catalog.public_catalog(db)
        assert len(public)==1 and len(public[0]['addresses'])==3
        assert 'detail_hint' not in str(public) and '内部备注' not in str(public)
        args=dict(customer_id=customer.id,region_id=county.id,address_book_id=address.id,
            address='spoofed',store_id=stores[1].id,estate='spoofed',description='repair')
        old=await create_order(db,OrderCreate(**args))
        assert old.store_id==stores[0].id and 'spoofed' not in old.address
        original_address=old.address
        await rejects(create_order(db,OrderCreate(**{**args,'address_book_id':None,'service_area_id':area_id})))
        saved=await create_address(db,AddressCreate(user_id=customer.id,service_address_id=address.id,
            contact_name='customer',contact_phone='19900000002'))
        assert saved.service_address_id==address.id
        demand=await create_demand(db,DomesticDemandCreate(customer_id=customer.id,region_id=county.id,
            address_book_id=address.id,address='spoofed',service_type='nanny',contact_name='C',contact_phone='19900000002'))
        assert demand.store_id==stores[0].id and demand.address==original_address
        from datetime import date
        from app.services.service_package import create_package,buy_package
        from app.schemas.service_package import ServicePackageCreate,CustomerPackageCreate
        package=await create_package(db,ServicePackageCreate(name='维护包',category='other',service_years=1,annual_times=1,device_count=1,service_month=12,price=100))
        purchased=await buy_package(db,CustomerPackageCreate(package_id=package.id,user_id=customer.id,
            store_id=stores[1].id,address_book_id=address.id,address='spoofed',contact_phone='19900000002',start_date=date(2026,11,1)))
        assert purchased.store_id==stores[0].id and purchased.address==original_address and purchased.address_book_id==address.id
        await rejects(update_store(db,stores[0],StoreUpdate(region_id=city.id)))
        await catalog.save_coverage(db,stores[0],[],admin.id)
        await rejects(catalog.resolve_address(db,address))
        await catalog.save_coverage(db,stores[1],[Scope(service_area_id=area_id)],admin.id)
        assert (await create_order(db,OrderCreate(**args))).store_id==stores[1].id
        assert old.store_id==stores[0].id and old.address==original_address
        stores[1].enabled=False;await db.commit()
        assert not await catalog.public_catalog(db)
        await rejects(create_order(db,OrderCreate(**args)))
        stores[1].enabled=True;await db.commit()
        ids=(admin.id,address.id)
        await rejects(import_entries(ImportEntries(items=[entry('9999'),entry('2605')]),db,admin))
        assert not (await db.execute(select(StoreAddress.id).where(StoreAddress.room=='9999'))).first()
        address=await db.get(StoreAddress,ids[1]);address.enabled=False;await db.commit()
        await rejects(catalog.resolve_address(db,address))
        print('PASS: central catalog, no-store creation, aliases, duplicates, hierarchical future coverage, overlap guard, server routing, saved addresses, domestic, transfer/history, suspended/deleted exclusion, atomic import')
    await engine.dispose()


if __name__=='__main__':asyncio.run(main())

