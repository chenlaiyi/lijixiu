"""Reservation data stays in the authenticated customer's own application list."""
import asyncio,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DATABASE_URL']='sqlite+aiosqlite:///:memory:'
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from fastapi import HTTPException
from app.models.base import Base
from app.models import User,UserRole,DomesticDemand
from app.routers.business import demands

async def main():
 engine=create_async_engine('sqlite+aiosqlite:///:memory:')
 async with engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
 async with async_sessionmaker(engine,expire_on_commit=False)() as db:
  users=[User(name='customer'+str(i),phone='1990000000'+str(i),role=UserRole.CUSTOMER) for i in [1,2]]
  db.add_all(users);await db.flush()
  for user in users:
   db.add(DomesticDemand(customer_id=user.id,created_by_user_id=user.id,region_id=1,
       service_type='maternity',contact_name=user.name,contact_phone=user.phone,address='private address',description='private request'))
  await db.commit()
  mine=await demands(customer_id=None,store_id=None,service_type=None,status=None,db=db,user=users[0])
  assert len(mine)==1 and mine[0].customer_id==users[0].id
  try:
   await demands(customer_id=users[1].id,store_id=None,service_type=None,status=None,db=db,user=users[0])
   raise AssertionError('Other customer data was exposed')
  except HTTPException as exc:assert exc.status_code==403
  print('PASS customer reservation list is private; cross-customer access rejected')
 await engine.dispose()

if __name__=='__main__':asyncio.run(main())
