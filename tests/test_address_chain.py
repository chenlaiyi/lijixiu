"""Isolated address-library -> saved-address -> order routing regression."""
import asyncio
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///:memory:'
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app import models
from app.models.base import Base
from app.models.user import User, UserRole
from app.models.region import Region
from app.models.store import Store, StoreStatus
from app.models.service_area import ServiceArea, ServiceAreaAssignment
from app.schemas.business import AddressCreate, AddressUpdate, AddressOut
from app.schemas.store import StoreAddressCreate
from app.schemas.order import OrderCreate
from app.services.business import create_address, update_address, list_addresses
from app.services.store import create_address as create_standard
from app.services.order import create_order
from app.services.service_area import customer_options
from app.routers.user import switch_active_role, ActiveRoleRequest

async def main():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        customer = User(name='customer', phone='19900000001', role=UserRole.CUSTOMER)
        manager = User(name='manager', phone='19900000002', role=UserRole.ADMIN, business_role='store_manager')
        region = Region(name='厦门市', level=1)
        db.add_all([customer,manager,region]); await db.flush()
        stores = [Store(name=name,region_id=region.id,manager_id=manager.id,status=StoreStatus.ACTIVE,enabled=True)
                  for name in ('未来海岸店','备用店')]
        db.add_all(stores); await db.flush()
        area=ServiceArea(code='TEST123',province='福建省',city='厦门市',district='海沧区',street='嵩屿街道',
                         name='未来海岸社区',source_name='test',source_url='',source_published_at='2026-10-24')
        db.add(area); await db.flush()
        assignment=ServiceAreaAssignment(service_area_id=area.id,primary_store_id=stores[0].id,manager_id=manager.id)
        db.add(assignment); await db.commit()
        fields=dict(service_area_id=area.id,estate='未来海岸-蓝月湾一期',door_number='嵩屿北五里23号2101室')
        saved=await create_address(db,AddressCreate(user_id=customer.id,contact_name='测试客户',contact_phone='19900000001',is_default=True,**fields))
        out=AddressOut.model_validate(saved)
        assert out.address=='厦门市 海沧区 未来海岸-蓝月湾一期 嵩屿北五里23号2101室'
        assert out.door_number==fields['door_number'] and out.city=='厦门市'
        standard=await create_standard(db,StoreAddressCreate(created_by_user_id=manager.id,**fields))
        assert standard.id==saved.service_address_id
        args=dict(customer_id=customer.id,region_id=region.id,description='repair',address='client supplied address')
        order=await create_order(db,OrderCreate(**args,store_id=stores[1].id,**fields))
        assert order.store_id==stores[0].id and order.address==out.address
        assert order.door_number==fields['door_number']
        # Existing saved addresses follow current coverage on the next order;
        # historical order snapshots remain unchanged.
        assignment.primary_store_id=stores[1].id;await db.commit()
        next_order=await create_order(db,OrderCreate(**args,address_book_id=standard.id))
        assert next_order.store_id==stores[1].id
        assert order.store_id==stores[0].id
        updated=await update_address(db,saved,AddressUpdate(**{**fields,'door_number':'嵩屿北五里23号2102室'}))
        assert updated.service_address_id!=standard.id
        assert '2102室' in updated.address and '2101室' in order.address
        assert (await list_addresses(db,customer.id))[0].estate==fields['estate']
        legacy=await create_standard(db,StoreAddressCreate(service_area_id=area.id,estate='老小区',
            building='23',unit='2',room='2101',created_by_user_id=manager.id))
        assert legacy.door_number=='23号楼2单元2101室'
        options=await customer_options(db)
        assert fields['estate'] in options[0]['estates'] and options[0]['store_id']==stores[1].id
        order.estate = '仅订单中出现的小区'
        await db.commit()
        assert order.estate in (await customer_options(db))[0]['estates']
        assert order.estate not in (await customer_options(db, include_order_estates=False))[0]['estates']
        # The mini-program sends business_role, not active_business_role.
        switched=await switch_active_role(manager.id,ActiveRoleRequest(business_role='store_manager'),db,manager)
        assert switched.active_business_role=='store_manager'
        try:
            await create_order(db,OrderCreate(**args,service_area_id=area.id,estate='未来海岸'))
            raise AssertionError('Missing door number was accepted')
        except ValueError: pass
        from app.schemas.store import StoreAddressUpdate
        from app.services.store import update_address as update_standard
        from app.routers.service_area import address_catalog
        from app.routers.store import delete_address
        leaf = await create_standard(db, StoreAddressCreate(service_area_id=area.id,
            estate='蓝月湾一期', building='S5栋', unit='', room='2605',
            door_number='嵩屿北五里27号2605室', aliases='厦门市海沧区蓝月湾一期S5栋2605室',
            detail_hint='内部核验备注', created_by_user_id=manager.id, source_name='贝壳'))
        leaf_id = leaf.id
        catalog = await address_catalog(db)
        public_leaf = next(row for row in catalog[0]['addresses'] if row['id'] == leaf_id)
        assert public_leaf['building']=='S5栋' and public_leaf['room']=='2605'
        assert 'detail_hint' not in public_leaf and 'created_by_user_id' not in public_leaf
        captured = await create_order(db, OrderCreate(**args, service_area_id=area.id,
            address_book_id=leaf_id, estate='伪造小区', door_number='伪造门牌'))
        assert captured.address_book_id==leaf_id and captured.estate=='蓝月湾一期'
        assert captured.door_number=='嵩屿北五里27号2605室'
        snapshot=captured.address
        saved_leaf = await create_address(db, AddressCreate(user_id=customer.id,
            contact_name='test',contact_phone='19900000001',service_area_id=area.id,
            service_address_id=leaf_id,estate='client label',door_number='client label'))
        assert saved_leaf.service_address_id==leaf_id
        duplicate = await create_standard(db, StoreAddressCreate(service_area_id=area.id,
            estate='蓝月湾一期',building='S5栋',room='2605',door_number='S5栋2605室',created_by_user_id=manager.id))
        assert duplicate.id==leaf_id
        await update_standard(db,leaf,StoreAddressUpdate(door_number='嵩屿北五里27号2605室',
            aliases='蓝月湾一期S5栋2605室\n嵩屿北五里27号2605室',detail_hint='已核实'))
        assert leaf.id==leaf_id and captured.address==snapshot
        await delete_address(leaf_id, db, manager)
        assert all(row['id']!=leaf_id for row in (await address_catalog(db))[0]['addresses'])
        try:
            await create_order(db,OrderCreate(**args,address_book_id=leaf_id,service_area_id=area.id))
            raise AssertionError('Deleted address remained selectable')
        except ValueError: pass
        assert captured.address==snapshot and captured.address_book_id==leaf_id
        print('PASS: unified address format, library reuse, saved-address edit, current routing, immutable order snapshots and legacy compatibility')
    await engine.dispose()

if __name__=='__main__': asyncio.run(main())
