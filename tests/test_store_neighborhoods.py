import asyncio
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///:memory:'
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app import models
from app.models.base import Base
from app.models.region import Region
from app.models.user import User, UserRole
from app.schemas.store import StoreCreate, StoreUpdate
from app.schemas.order import OrderCreate
from app.services.store import create_store, update_store, save_store_coverage, store_coverage
from app.services.service_area import customer_options
from app.services.order import create_order


async def main():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as connection: await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        manager = User(name='manager',phone='19900000001',role=UserRole.ADMIN,business_role='platform_admin')
        customer = User(name='customer',phone='19900000002',role=UserRole.CUSTOMER,business_role='customer')
        city=Region(name='厦门市',level=1)
        db.add_all([manager,customer,city]);await db.flush()
        district=Region(name='海沧区',level=2,parent_id=city.id)
        other=Region(name='集美区',level=2,parent_id=city.id)
        db.add_all([district,other]);await db.commit()
        try:
            await create_store(db,StoreCreate(name='bad',region_id=city.id,manager_id=manager.id))
            raise AssertionError('City-level store was accepted')
        except ValueError: pass
        stores=[]
        for name in ['店A','店B']:
            store=await create_store(db,StoreCreate(name=name,region_id=district.id,manager_id=manager.id))
            await update_store(db,store,StoreUpdate(enabled=True));stores.append(store)
        assigned=await save_store_coverage(db,stores[0],['蓝月湾一期','浪琴湾'],manager.id)
        await save_store_coverage(db,stores[1],['蓝月湾二期'],manager.id)
        assert len(await customer_options(db))==3
        try:
            await save_store_coverage(db,stores[1],['蓝月湾一期','冲突时不应创建'],manager.id)
            raise AssertionError('Conflicting coverage accepted')
        except ValueError: pass
        assert len(await store_coverage(db,stores[1]))==1
        area=next(a for a in assigned if a['name']=='蓝月湾一期')
        args=dict(customer_id=customer.id,region_id=district.id,service_area_id=area['id'],estate='蓝月湾一期',door_number='S5栋2605室',description='repair',address='ignored')
        old=await create_order(db,OrderCreate(**args));assert old.store_id==stores[0].id
        try:
            await update_store(db,stores[0],StoreUpdate(region_id=other.id))
            raise AssertionError('District moved while assigned')
        except ValueError: pass
        await save_store_coverage(db,stores[0],[],manager.id)
        await save_store_coverage(db,stores[1],['蓝月湾一期','蓝月湾二期'],manager.id)
        new=await create_order(db,OrderCreate(**args));assert new.store_id==stores[1].id
        assert old.store_id==stores[0].id
        await update_store(db,stores[0],StoreUpdate(region_id=other.id,name='新店名',remark='saved'))
        assert stores[0].region_id==other.id and stores[0].name=='新店名'
        print('PASS: district-only stores; per-neighborhood routing; conflict atomicity; save/edit; explicit reassignment and immutable historical orders')
    await engine.dispose()

if __name__=='__main__': asyncio.run(main())
