"""File previews, idempotency, entrance scopes and source-ID collision protection."""
import asyncio,csv,io,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DATABASE_URL']='sqlite+aiosqlite:///:memory:'
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.models.base import Base
from app.models import User,UserRole,Region,Store,StoreStatus,StoreAddress,ServiceArea
from app.services.catalog_import import make_plan,apply_plan
from app.services.catalog_files import HEADERS,read_file
from app.services.address_catalog import save_coverage,public_catalog
from app.routers.address_catalog import Scope


def fixture():
    rows=[]
    for number,house in [('28','HOUSE-A'),('30','HOUSE-B')]:
        rows.append({'城市':'厦门市','区县':'海沧区','立即修小区编号':'3911057502760','小区名称':'未来海岸蓝月湾一期',
            '贝壳小区ID':'3911057502760','小区别名':'蓝月湾','楼栋名称':'S6号楼','贝壳楼栋ID':'BUILDING-S6',
            '原始单元名称':'嵩屿北五里'+number,'入口类型':'道路门牌','道路门牌标准写法':'嵩屿北五里'+number+'号',
            '贝壳单元ID':'UNIT-'+number,'房号':'101','贝壳房屋ID':house,'房屋类型':'住宅',
            '同址别名':'未来海岸蓝月湾一期S6号楼101室'})
    return rows


async def main():
    engine=create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as c:await c.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine,expire_on_commit=False)() as db:
        user=User(name='admin',phone='19900000001',role=UserRole.ADMIN,business_role='platform_admin')
        city=Region(name='厦门市',level=1);db.add_all([user,city]);await db.flush()
        county=Region(name='海沧区',level=2,parent_id=city.id);db.add(county);await db.commit()
        rows=fixture();blob=json.dumps({'import_address':rows},ensure_ascii=False).encode()
        stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=HEADERS);writer.writeheader();writer.writerows(rows)
        parsed,_=read_file('test.csv',stream.getvalue().encode('utf-8-sig'));assert parsed[0]['贝壳房屋ID']=='HOUSE-A'
        preview,_=await make_plan(db,'test.json',blob)
        assert preview['created']==2 and preview['can_apply'] and preview['alias_qualified']==2
        assert await db.scalar(select(func.count(StoreAddress.id)))==0
        report=await apply_plan(db,'test.json',blob,user.id,preview['file_hash']);assert report['created']==2
        addresses=(await db.execute(select(StoreAddress).order_by(StoreAddress.id))).scalars().all()
        assert len({a.full_address for a in addresses})==2 and len({a.aliases for a in addresses})==2
        assert not await public_catalog(db)
        addresses[0].detail_hint='人工备注';addresses[0].enabled=False;await db.commit()
        repeat,_=await make_plan(db,'test.json',blob);assert repeat['skipped']==2
        await apply_plan(db,'test.json',blob,user.id,repeat['file_hash'])
        assert addresses[0].detail_hint=='人工备注' and not addresses[0].enabled
        conflict=[{**rows[0],'房号':'102'}]
        bad,_=await make_plan(db,'bad.json',json.dumps(conflict).encode());assert not bad['can_apply']
        duplicate,_=await make_plan(db,'bad.json',json.dumps(rows+rows[:1]).encode());assert not duplicate['can_apply']
        wrong=[{**rows[0],'立即修小区编号':'OTHER','贝壳小区ID':'OTHER','贝壳房屋ID':'OTHER-HOME'}]
        bad,_=await make_plan(db,'bad.json',json.dumps(wrong).encode());assert not bad['can_apply']
        try:await apply_plan(db,'test.json',blob,user.id,'wrong-hash');raise AssertionError('changed file accepted')
        except ValueError:pass
        addresses[0].enabled=True
        stores=[Store(name=n,region_id=county.id,manager_id=user.id,enabled=True,status=StoreStatus.ACTIVE) for n in ['A','B']]
        db.add_all(stores);await db.commit()
        area_id=addresses[0].service_area_id
        await save_coverage(db,stores[0],[Scope(service_area_id=area_id,building='S6号楼',entrance_name='嵩屿北五里28号')],user.id)
        await save_coverage(db,stores[1],[Scope(service_area_id=area_id,building='S6号楼',entrance_name='嵩屿北五里30号')],user.id)
        public=await public_catalog(db);assert {r['store_id'] for r in public[0]['addresses']}=={s.id for s in stores}
        try:await save_coverage(db,stores[1],[Scope(service_area_id=area_id,building='S6号楼')],user.id);raise AssertionError('overlapping entrance accepted')
        except ValueError:pass
        print('PASS preview without writes, CSV/JSON source IDs, unique entrances, repeat skip preserves manual changes, conflicts, file hash and nonoverlapping entrance coverage')
    await engine.dispose()


if __name__=='__main__':asyncio.run(main())
