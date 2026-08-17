"""add user agreement and login fields

Revision ID: 9d3a7b8c4e21
Revises: 985b36c09a76
Create Date: 2026-08-14 23:30:00.000000+08:00

为什么需要这个迁移:
1. 生产库 (8.134.99.53) 从未跑过 alembic upgrade,users 表缺 5 个字段
   (agreed_terms_version / agreed_privacy_version / agreed_at /
    deletion_requested_at / deletion_scheduled_at)。
   initial_schema(985b36c09a76) 已声明这些字段,但生产没应用。
2. 新增 last_login_at 字段,记录每次登录时间(2026-08-14 加,
   解决"系统不知道有没有人登录"的产品债)。

生产部署顺序:
  alembic stamp 985b36c09a76     # 标记 initial 已应用(实际只跑了部分)
  alembic upgrade head           # 跑这个迁移,加 6 字段

注意:
- SQLite 用 batch_alter_table(env.py 已配 render_as_batch=True)
- 6 个字段都 nullable,不需要默认值,不影响现有数据
- downgrade 全部 DROP COLUMN(老 SQLite 不支持 DROP COLUMN,会报错,需要重建表)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9d3a7b8c4e21'
down_revision = '985b36c09a76'
branch_labels = None
depends_on = None


# 2026-08-14: 幂等设计
# - dev: 5 字段已存在(progress.md 提过"alembic stamp head + 手动 ALTER"),
#        last_login_at 不存在
# - 生产: 5 字段不存在(production 从未跑 alembic),last_login_at 也不存在
# 用 SQLAlchemy inspect 查现有列,只加不存在的


def upgrade() -> None:
    # 2026-08-14: 幂等设计 — 用 PRAGMA table_info 替代 sa.inspect(后者在 alembic offline 模式下不可用)
    # - dev: 5 字段已存在(progress.md 提过"alembic stamp head + 手动 ALTER"),
    #        last_login_at 不存在
    # - 生产: 5 字段不存在(production 从未跑 alembic),last_login_at 也不存在
    conn = op.get_bind()
    existing = set()
    try:
        # PRAGMA table_info 返回 (cid, name, type, notnull, dflt_value, pk)
        rows = conn.exec_driver_sql('PRAGMA table_info(users)').fetchall()
        existing = {r[1] for r in rows}
    except Exception:
        # 真 offline 模式(没真连接)时 — 不判断,全加(输出 static SQL)
        # 这样 dev 真跑会因列已存在而报错,但 dev 用 PRAGMA 走真连接,正常
        pass

    with op.batch_alter_table('users', schema=None) as batch_op:
        # 5 个补字段(生产缺,dev 已有)
        if 'agreed_terms_version' not in existing:
            batch_op.add_column(sa.Column('agreed_terms_version', sa.String(length=20), nullable=True))
        if 'agreed_privacy_version' not in existing:
            batch_op.add_column(sa.Column('agreed_privacy_version', sa.String(length=20), nullable=True))
        if 'agreed_at' not in existing:
            batch_op.add_column(sa.Column('agreed_at', sa.DateTime(timezone=True), nullable=True))
        if 'deletion_requested_at' not in existing:
            batch_op.add_column(sa.Column('deletion_requested_at', sa.DateTime(timezone=True), nullable=True))
        if 'deletion_scheduled_at' not in existing:
            batch_op.add_column(sa.Column('deletion_scheduled_at', sa.DateTime(timezone=True), nullable=True))
        # 1 个新字段(活跃度追踪)
        if 'last_login_at' not in existing:
            batch_op.add_column(sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))
            batch_op.create_index(batch_op.f('ix_users_last_login_at'), ['last_login_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_last_login_at'))
        batch_op.drop_column('last_login_at')
        batch_op.drop_column('deletion_scheduled_at')
        batch_op.drop_column('deletion_requested_at')
        batch_op.drop_column('agreed_at')
        batch_op.drop_column('agreed_privacy_version')
        batch_op.drop_column('agreed_terms_version')
