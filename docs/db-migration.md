# DB Migration 指南 (alembic)

> 2026-08-09 落地 · 全自动从 SQLAlchemy metadata 生成迁移 · 兼容 SQLite + MySQL

## 为什么上 alembic

之前项目用 `Base.metadata.create_all()` 一次性建表,生产环境要改 schema 时:

- 没历史记录,谁加的列、加了啥?
- SQLite / MySQL 切换时没统一入口
- 数据迁移(默认值填充 / 索引重建)没有工具链

现在统一走 alembic,所有 schema 改动可追溯、可回滚、可灰度。

## 文件结构

```
.
├── alembic.ini                     # alembic 主配置(指向 migrations/)
├── migrations/
│   ├── env.py                      # 加载 .env,自动从 app.models 拿 metadata
│   ├── script.py.mako              # 迁移文件模板
│   └── versions/
│       └── 2026_08_09_1419-985b36c09a76_initial_schema.py    # 初始 40 张表
└── app/models/
    ├── base.py                     # 抽出来的 DeclarativeBase,让 alembic 不触发 async engine
    ├── __init__.py                 # import 所有 model(填满 Base.metadata)
    └── *.py                        # 22 个 SQLAlchemy model
```

## 配置(`.env`)

`migrations/env.py` 会自动读 `DATABASE_URL`,支持:

| URL 形式 | 驱动 | 备注 |
|---|---|---|
| `sqlite+aiosqlite:///./dev.db` | aiosqlite → sqlite3 | 本地开发,自动去 `+aiosqlite` |
| `mysql+aiomysql://root:pwd@host:3306/db` | aiomysql → pymysql | 生产,自动 `+pymysql` |
| `postgresql+asyncpg://...` | asyncpg → psycopg2 | 备选 |

最小 `.env` 例子:

```env
# 本地开发
DATABASE_URL=sqlite+aiosqlite:///./dev.db

# 生产 MySQL
# DATABASE_URL=mysql+aiomysql://xiulijiu:STRONG_PWD@127.0.0.1:3306/xiulijiu
```

## 常用命令

```bash
# 1) 应用所有迁移(到最新)
alembic upgrade head

# 2) 回滚一步
alembic downgrade -1

# 3) 回滚到头
alembic downgrade base

# 4) 当前版本
alembic current

# 5) 历史
alembic history --verbose

# 6) 看下一条会跑什么 SQL(不执行)
alembic upgrade head --sql

# 7) 自动生成新迁移(对比 metadata 与 DB 现状)
alembic revision --autogenerate -m "add foo column"
```

## 改 schema 的标准流程

1. 改 `app/models/*.py`(加列 / 改类型 / 加索引)
2. 跑 `alembic revision --autogenerate -m "descriptive message"`
3. **人眼审**生成的 `migrations/versions/*.py`,alembic 不是银弹
   - 它不会改 enum 值
   - 它可能漏 server_default / check constraint
   - rename 列会变成 drop+add,要手动改写成 `alter_column`
4. 跑 `alembic upgrade head` 验证
5. 跑 `tests/test_alembic_migration.py` 端到端验证
6. 跑全套测试确认无回归
7. 提交,CI 跑,部署

## 已落地的迁移(2026-08-09)

| revision | 内容 | 表数 |
|---|---|---|
| `985b36c09a76` | initial schema | 40 张表 |

覆盖:users / wallets / ledgers / orders / pay_orders / refund_orders / withdrawals / profit_shares / repairers / regions / stores / store_staff / store_addresses / service_areas / service_area_assignments / service_area_assignment_logs / service_bills / service_packages / customer_packages / package_schedules / settlement_periods / settlement_items / idempotency_keys / reconciliation_logs / alert_events / distributed_locks / support_tickets / support_replies / wage_records / warranty_certificates / phone_verification_codes / order_access_tokens / order_logs / customer_addresses / area_open_requests / domestic_workers / domestic_demands / domestic_candidates / domestic_contracts / domestic_payment_stages

## 测试覆盖(`tests/test_alembic_migration.py`)

22 个 case 端到端验证:

- `alembic-upgrade-head` — 能建 40 张表
- `tables-count-geq-30` — 表数 ≥ 30(防漏表)
- 17 个 `table-<name>` — 关键表必须存在
- `alembic-upgrade-idempotent` — 二次 upgrade 不报错
- `alembic-downgrade-base` — 全部回滚
- `downgrade-removed-business-tables` — 回滚后表真的清空
- `alembic-upgrade-after-downgrade` — 回滚后再升级能恢复
- `upgrade-restored-all-tables` — 升级前后表数一致

## SQLite ↔ MySQL 切换

1. 改 `.env` 的 `DATABASE_URL`
2. `alembic upgrade head`
3. 启动服务

数据迁移用 `scripts/migrate_sqlite_to_mysql.py`(已就绪)。

## 注意事项

- **不要在生产手动改表结构**,所有改动必须走迁移
- **不要删除已部署的 revision 文件**,会破坏历史链
- 多分支同时改 schema 时,先 rebase 再生成新 migration,避免 hash 冲突
- 改 enum 值的迁移 alembic 不会自动生成,得手写 `op.execute("ALTER TYPE ...")`
