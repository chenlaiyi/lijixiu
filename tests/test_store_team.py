import asyncio,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));os.environ['DATABASE_URL']='sqlite+aiosqlite:///:memory:'
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy import select
from app.models.base import Base
from app.models import User,UserRole,Region,Store,StoreStatus
from app.models.repairer import Repairer
from app.models.order import Order,OrderStatus
from app.models.settlement import SettlementItem
from app.services.store_team import team,validate_member
from app.services.order import manual_assign,list_orders
from app.routers.store import save_technicians,TeamUpdate,order_alerts
from app.services.business import create_payroll
from app.schemas.business import PayrollCreate,PayrollLine
async def main():
 e=create_async_engine('sqlite+aiosqlite:///:memory:')
 async with e.begin() as c:await c.run_sync(Base.metadata.create_all)
 async with async_sessionmaker(e,expire_on_commit=False)() as db:
  admin=User(name='admin',phone='19900000111',role=UserRole.ADMIN,business_role='platform_admin');worker=User(name='worker',phone='19900000112',role=UserRole.REPAIRER);city=Region(name='City',level=1);other=Region(name='Other',level=1);db.add_all([admin,worker,city,other]);await db.flush()
  county=Region(name='County',level=2,parent_id=city.id);db.add(county);await db.flush()
  stores=[Store(name=n,region_id=county.id,manager_id=admin.id,status=StoreStatus.ACTIVE,enabled=True) for n in ['one','two']];r=Repairer(user_id=worker.id,skills='repair',region_id=city.id);db.add_all(stores+[r]);await db.commit()
  for s in stores:await save_technicians(s.id,TeamUpdate(repairer_ids=[r.id]),db,admin)
  for s in stores:assert (await team(db,s))[0].id==r.id;await validate_member(db,s.id,r.id)
  orders=[Order(customer_id=admin.id,store_id=s.id,region_id=county.id,address='test',description='test',status=OrderStatus.STORE_ACCEPTED,price=100) for s in stores];db.add_all(orders);await db.commit()
  for o in orders:await manual_assign(db,o,r.id)
  mine=await list_orders(db,repairer_id=r.id);assert {o.id for o in mine}=={o.id for o in orders};assert all(o.repairer_id is None for o in mine)
  for i,s in enumerate(stores):await create_payroll(db,PayrollCreate(month='2026-11',store_id=s.id,manager_id=admin.id,lines=[PayrollLine(employee_user_id=worker.id,amount=100+i)]))
  amounts={x.store_id:x.amount for x in (await db.execute(select(SettlementItem))).scalars()};assert amounts=={stores[0].id:100,stores[1].id:101}
  await save_technicians(stores[0].id,TeamUpdate(repairer_ids=[]),db,admin);assert not await team(db,stores[0]);assert await team(db,stores[1]);assert len(await list_orders(db,repairer_id=r.id))==2
  assert len((await db.execute(select(SettlementItem))).scalars().all())==2
  r.region_id=other.id;await db.commit()
  try:await validate_member(db,stores[1].id,r.id);raise AssertionError('cross-city assignment accepted')
  except ValueError:pass
  print('PASS multi-store membership, assigned-but-unaccepted job visibility, per-store monthly wages, removal preserves history, cross-city assignment rejected')
 await e.dispose()
asyncio.run(main())
