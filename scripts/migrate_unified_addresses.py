"""One-time conservative migration, run against a backup first. Never deletes history."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select,text
from app.core.database import init_db,async_session,engine
from app.models.store import AddressCoverage,StoreAddress,Store
from app.models.service_area import ServiceArea,ServiceAreaAssignment
from app.services.address_catalog import estate_area


async def main():
    await init_db()
    async with async_session() as db:
        await db.execute(text('CREATE TABLE IF NOT EXISTS app_schema_versions (name VARCHAR(100) PRIMARY KEY)'))
        done=(await db.execute(text("SELECT name FROM app_schema_versions WHERE name='unified-addresses-v1'"))).first()
        if done:
            print('unified-addresses-v1 already applied')
            return
        rows=(await db.execute(select(StoreAddress))).scalars().all()
        assignments=(await db.execute(select(ServiceAreaAssignment))).scalars().all()
        rules=[]
        for row in rows:
            area=await estate_area(db,row.region_id,row.estate)
            row.service_area_id=area.id
            # Existing catalog entries remain the same entity; private entries stay private.
            if row.store_id:
                rules.append((row.store_id,area.id,None,row.id,row.created_by_user_id))
        for assignment in assignments:
            area=await db.get(ServiceArea,assignment.service_area_id)
            store=await db.get(Store,assignment.primary_store_id) if assignment.primary_store_id else None
            if area and area.area_type=='estate' and store:
                rules=[r for r in rules if not (r[0]==store.id and r[1]==area.id)]
                rules.append((store.id,area.id,None,None,assignment.updated_by_user_id or store.manager_id))
        for store_id,area_id,building,address_id,operator in rules:
            store=await db.get(Store,store_id)
            db.add(AddressCoverage(store_id=store_id,service_area_id=area_id,building=building,
                address_id=address_id,operator_id=operator or store.manager_id))
        await db.execute(text("INSERT INTO app_schema_versions(name) VALUES ('unified-addresses-v1')"))
        await db.flush()
        if (await db.execute(text('PRAGMA foreign_key_check'))).all():
            raise RuntimeError('Foreign key check failed')
        await db.commit()
        print(json.dumps(dict(addresses_preserved=len(rows),coverage_rules=len(rules)),ensure_ascii=False))
    await engine.dispose()


if __name__=='__main__':asyncio.run(main())
