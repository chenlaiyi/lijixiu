"""Alembic 环境配置(2026-08-09)。

- 从 .env / settings 读 DATABASE_URL(SQLite 或 MySQL 都支持)
- 自动从 SQLAlchemy metadata 生成迁移
- 离线模式(纯 SQL 输出)+ 在线模式(直连 DB)
- 兼容 async 引擎:自动把 async URL 转为 sync URL(aiosqlite → sqlite3,asyncpg → psycopg2)
"""
import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# 2026-08-09: 读 .env / 项目 settings
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env(同目录或父目录)
for env_path in [Path(__file__).resolve().parent.parent / '.env']:
    if env_path.exists():
        load_dotenv(env_path, override=False)
        break

# 此配置是 alembic 注入的对象
config = context.config

# 从环境变量读 DATABASE_URL
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    # 2026-08-09: 兼容 async 驱动(alembic 走 sync)
    sync_url = DATABASE_URL
    sync_url = re.sub(r'\+aiosqlite', '', sync_url)  # aiosqlite → sqlite3
    sync_url = re.sub(r'\+asyncpg', '+psycopg2', sync_url)
    sync_url = re.sub(r'\+aiomysql', '+pymysql', sync_url)
    config.set_main_option('sqlalchemy.url', sync_url)

# 配置日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 2026-08-09: 引入项目 metadata(只 import Base + models,不动 engine)
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from app.models.base import Base
import app.models  # 触发所有模型 import(它们都继承自 app.models.base.Base)
# app/models/__init__.py 已经 import 了所有模型,Base.metadata 自动收集

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式:只输出 SQL,不连 DB。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,  # SQLite ALTER TABLE 兼容
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式:连真 DB 跑迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=True,  # SQLite ALTER TABLE 兼容
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
