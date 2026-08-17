"""SQLAlchemy declarative base — 独立模块,避免 import database.py 触发 engine。

2026-08-09: 抽出,让 alembic env.py 能干净 import metadata。
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
