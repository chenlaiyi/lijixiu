import asyncio
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DATABASE_URL']='sqlite+aiosqlite:///:memory:'
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app import models
from app.models.base import Base
from app.models.user import User,UserRole
from app.models.store import Store
from app.schemas.region import RegionCreate,RegionUpdate
from app.services.region import create_region,update_region,delete_region,get_region


async def rejects(call):
    try: await call
    except ValueError: return
    raise AssertionError('Expected guarded operation to be rejected')


async def main():
    engine=create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as c:await c.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine,expire_on_commit=False)() as db:
        user=User(name='admin',phone='19900000001',role=UserRole.ADMIN,business_role='platform_admin')
        db.add(user);await db.commit()
        city=await create_region(db,RegionCreate(name='厦门市',level=1))
        await rejects(create_region(db,RegionCreate(name=' 厦门市 ',level=1)))
        await rejects(create_region(db,RegionCreate(name='海沧区',level=2)))
        county=await create_region(db,RegionCreate(name='海沧区',level=2,parent_id=city.id))
        await rejects(delete_region(db,city))
        await rejects(update_region(db,city,RegionUpdate(parent_id=city.id)))
        await update_region(db,county,RegionUpdate(manager_id=user.id))
        assert county.manager_id==user.id
        await update_region(db,county,RegionUpdate(manager_id=None))
        assert county.manager_id is None
        await rejects(update_region(db,county,RegionUpdate(manager_id=99999)))
        store=Store(name='store',region_id=county.id,manager_id=user.id)
        db.add(store);await db.commit()
        await rejects(delete_region(db,county))
        await rejects(update_region(db,county,RegionUpdate(name='new county')))
        await update_region(db,county,RegionUpdate(manager_id=user.id))
        unused=await create_region(db,RegionCreate(name='未使用城市',level=1))
        await update_region(db,unused,RegionUpdate(name='集美区',level=2,parent_id=city.id))
        assert unused.level==2 and unused.parent_id==city.id
        unused_id=unused.id
        await delete_region(db,unused)
        assert await get_region(db,unused_id) is None
        print('PASS: region edit/save/delete, nullable manager, valid parent levels, duplicate prevention and referenced-region protection')
    await engine.dispose()

if __name__=='__main__':asyncio.run(main())
