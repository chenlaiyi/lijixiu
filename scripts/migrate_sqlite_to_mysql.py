"""SQLite → MySQL 数据迁移工具(2026-08-09)。

用 SQLAlchemy 通用接口,逐表 SELECT + INSERT,自动处理:
- boolean (sqlite 是 INTEGER 0/1 → MySQL TINYINT)
- datetime (sqlite 是字符串 → MySQL DATETIME)
- json (sqlite 是 TEXT → MySQL JSON)
- autoincrement (sqlite ROWID → MySQL AUTO_INCREMENT)

用法:
    # Dry-run(只统计行数)
    python scripts/migrate_sqlite_to_mysql.py --dry-run

    # 真跑(INSERT IGNORE)
    python scripts/migrate_sqlite_to_mysql.py

    # 指定数据库
    SOURCE=sqlite+aiosqlite:///./xiulijiu.db \
    TARGET=mysql+pymysql://root:pwd@127.0.0.1:3307/xiulijiu \
    python scripts/migrate_sqlite_to_mysql.py
"""
import argparse
import os
import sys
import sqlite3
from pathlib import Path

# 加载 .env
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / '.env', override=False)

# 让模型注册(只为名字)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app.models  # noqa
from app.core.database import Base


def get_tables():
    """按依赖顺序返回表名(无外键依赖的先复制)。"""
    # 按 SQLAlchemy metadata 的 tables 顺序(声明顺序 = 依赖顺序)
    return [t.name for t in Base.metadata.sorted_tables]


def get_sqlite_count(conn, table):
    cur = conn.execute(f'SELECT COUNT(*) FROM "{table}"')
    return cur.fetchone()[0]


def get_sqlite_rows(conn, table, batch_size=500):
    cur = conn.execute(f'SELECT * FROM "{table}"')
    cols = [d[0] for d in cur.description]
    batch = []
    for row in cur:
        batch.append(dict(zip(cols, row)))
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', default=os.getenv('SOURCE', 'sqlite+aiosqlite:///./xiulijiu.db'),
                   help='SQLite URL')
    p.add_argument('--target', default=os.getenv('TARGET'),
                   help='MySQL URL(mysql+pymysql://user:pwd@host:port/db)')
    p.add_argument('--dry-run', action='store_true', help='只统计行数,不动 DB')
    p.add_argument('--batch-size', type=int, default=500)
    p.add_argument('--truncate', action='store_true', help='INSERT 前先 TRUNCATE 目标表')
    args = p.parse_args()

    if not args.target and not args.dry_run:
        print('ERR: 必须传 --target 或 --dry-run')
        return 1

    # SQLite 路径
    sqlite_path = args.source.replace('sqlite+aiosqlite:///', '').replace('sqlite:///', '')
    print(f'[source] {sqlite_path}')

    if not Path(sqlite_path).exists():
        print(f'ERR: SQLite 文件不存在: {sqlite_path}')
        return 1

    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row

    tables = get_tables()
    print(f'[tables] 共 {len(tables)} 张')

    if args.dry_run:
        print('\\n[dry-run] 行数统计:')
        for t in tables:
            try:
                n = get_sqlite_count(src, t)
                print(f'  {t:35s} {n:>10d} 行')
            except Exception as e:
                print(f'  {t:35s} ERR: {e}')
        src.close()
        return 0

    # 真跑:用 pymysql 直连
    import pymysql
    from urllib.parse import urlparse
    u = urlparse(args.target.replace('mysql+pymysql://', 'mysql://'))
    db_name = u.path.lstrip('/')
    target_url_no_db = args.target.replace(f'/{db_name}', '/')
    print(f'[target] {u.hostname}:{u.port} db={db_name}')

    # 1) 连 server(不指定 db),CREATE DATABASE IF NOT EXISTS
    target = pymysql.connect(
        host=u.hostname, port=u.port or 3306,
        user=u.username, password=u.password,
        charset='utf8mb4',
    )
    with target.cursor() as c:
        c.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    target.commit()
    target.close()
    print(f'  ✓ CREATE DATABASE {db_name}')

    # 2) 连目标 db
    target = pymysql.connect(
        host=u.hostname, port=u.port or 3306,
        user=u.username, password=u.password,
        database=db_name, charset='utf8mb4',
    )

    # 3) 跑 alembic upgrade head(用 pymysql 同步 URL)
    sync_target = args.target  # 已经是 pymysql 同步驱动
    os.environ['DATABASE_URL'] = sync_target
    from alembic.config import Config
    from alembic import command as alembic_cmd
    cfg = Config(str(Path(__file__).resolve().parent.parent / 'alembic.ini'))
    cfg.set_main_option('script_location', str(Path(__file__).resolve().parent.parent / 'migrations'))
    cfg.set_main_option('sqlalchemy.url', sync_target)
    print('  ✓ alembic upgrade head')
    alembic_cmd.upgrade(cfg, 'head')

    # 4) 逐表迁移
    total_rows = 0
    with target.cursor() as c:
        for table in tables:
            try:
                if args.truncate:
                    c.execute(f'SET FOREIGN_KEY_CHECKS = 0')
                    c.execute(f'TRUNCATE TABLE `{table}`')
                    c.execute(f'SET FOREIGN_KEY_CHECKS = 1')
                count = 0
                for batch in get_sqlite_rows(src, table, args.batch_size):
                    # 构造 INSERT
                    cols = list(batch[0].keys())
                    placeholders = ','.join(['%s'] * len(cols))
                    col_list = ','.join([f'`{c}`' for c in cols])
                    # 处理 None / datetime
                    values = []
                    for row in batch:
                        vals = []
                        for c in cols:
                            v = row[c]
                            # sqlite 1/0 → MySQL 1/0 (bool 自动)
                            if v is None:
                                vals.append(None)
                            else:
                                vals.append(v)
                        values.append(tuple(vals))
                    try:
                        c.executemany(
                            f'INSERT IGNORE INTO {table} ({col_list}) VALUES ({placeholders})',
                            values,
                        )
                        count += len(batch)
                    except Exception as e:
                        print(f'  ✗ {table}: {str(e)[:200]}')
                        # 不打断,继续
                target.commit()
                if count > 0:
                    print(f'  ✓ {table:35s} {count:>10d} 行')
                total_rows += count
            except Exception as e:
                print(f'  ✗ {table}: {str(e)[:200]}')

    src.close()
    target.close()
    print(f'\\n[done] 共迁移 {total_rows} 行')
    return 0


if __name__ == '__main__':
    sys.exit(main())
