"""Use the same preview/apply rules as the admin upload, without assigning any store."""
import argparse,asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.database import init_db,async_session,engine
from app.models.user import User
from app.services.catalog_import import make_plan,apply_plan


async def run(args):
    await init_db()
    file=Path(args.file);content=file.read_bytes()
    async with async_session() as db:
        user=await db.get(User,args.operator_id)
        if not user or not user.is_active or 'platform_admin' not in user.business_roles:
            raise ValueError('必须指定有效的平台管理员作为导入操作人')
        report,_=await make_plan(db,file.name,content)
        if args.expected_rows is not None and report['total']!=args.expected_rows:
            raise ValueError('导入行数与指定数量不符')
        if args.apply:
            if not args.expected_hash:raise ValueError('正式导入必须提供预览文件散列 --expected-hash')
            report=await apply_plan(db,file.name,content,user.id,args.expected_hash)
        print(json.dumps(report,ensure_ascii=False))
    await engine.dispose()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file',required=True)
    parser.add_argument('--operator-id',required=True,type=int)
    parser.add_argument('--expected-rows',type=int)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--expected-hash')
    asyncio.run(run(parser.parse_args()))
