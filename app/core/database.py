"""Database connection and lightweight startup migrations."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..models.base import Base  # 2026-08-09: 抽到独立模块,alembic env.py 可以干净 import
from .config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    """Create all tables and apply additive migrations for old SQLite/MySQL DBs."""

    from ..models import (  # noqa: F401
        AlertEvent,
        AreaOpenRequest,
        CustomerPackage,
        CustomerAddress,
        DistributedLockRecord,
        DomesticCandidate,
        DomesticContract,
        DomesticDemand,
        DomesticPaymentStage,
        DomesticWorker,
        IdempotencyKey,
        Ledger,
        Order,
        OrderAccessToken,
        PhoneVerificationCode,
        OrderLog,
        PackageSchedule,
        PayOrder,
        ProfitShare,
        ReconciliationLog,
        RefundOrder,
        Region,
        Repairer,
        ServiceBill,
        ServiceArea,
        ServiceAreaAssignment,
        ServiceAreaAssignmentLog,
        ServicePackage,
        SettlementItem,
        SettlementPeriod,
        Store,
        StoreAddress,
        StoreStaff,
        SupportReply,
        SupportTicket,
        User,
        UserRoleGrant,
        Wallet,
        WageRecord,
        WarrantyCertificate,
        Withdrawal,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.connect() as conn:
        migrations = [
            ("orders", "assigned_repairer_id", "INTEGER REFERENCES repairers(id)"),
            ("orders", "assigned_at", "DATETIME"),
            ("regions", "manager_id", "INTEGER REFERENCES users(id)"),
            ("users", "promotion_manager_id", "INTEGER REFERENCES users(id)"),
            ("users", "is_promotion_manager", "BOOLEAN DEFAULT 0"),
            ("users", "wechat_openid", "VARCHAR(128)"),
            ("users", "business_role", "VARCHAR(30) DEFAULT 'customer'"),
            # 2026-10-07 multi-role: 一个账号可同时拥有店长/师傅/业务等多个角色
            ("users", "business_roles", "JSON"),
            ("users", "active_business_role", "VARCHAR(30)"),
            # 2026-10-07:这几列只有 alembic 迁移里有,而生产库历史上「从未跑过
            # alembic」(见 2026_08_14 迁移注释)。补进轻量迁移,保证
            # create_all + 轻量迁移就能把老库带到现在,不会 500。
            ("users", "agreed_terms_version", "VARCHAR(20)"),
            ("users", "agreed_privacy_version", "VARCHAR(20)"),
            ("users", "agreed_at", "DATETIME"),
            ("users", "deletion_requested_at", "DATETIME"),
            ("users", "deletion_scheduled_at", "DATETIME"),
            ("users", "last_login_at", "DATETIME"),
            ("users", "avatar", "VARCHAR(500)"),
            ("orders", "store_id", "INTEGER REFERENCES stores(id)"),
            ("orders", "source", "VARCHAR(20) DEFAULT 'repair'"),
            ("orders", "address_book_id", "INTEGER REFERENCES store_addresses(id)"),
            ("orders", "address_code_snapshot", "VARCHAR(40)"),
            ("orders", "address_owner_user_id", "INTEGER REFERENCES users(id)"),
            ("orders", "service_area_id", "INTEGER REFERENCES service_areas(id)"),
            ("orders", "service_area_assignment_id", "INTEGER"),
            ("orders", "service_area_manager_id", "INTEGER REFERENCES users(id)"),
            ("orders", "service_area_district_snapshot", "VARCHAR(60)"),
            ("orders", "service_area_street_snapshot", "VARCHAR(80)"),
            ("orders", "service_area_name_snapshot", "VARCHAR(120)"),
            ("orders", "contact_phone", "VARCHAR(20)"),
            ("orders", "media_json", "TEXT"),
            ("orders", "address_changed", "BOOLEAN DEFAULT 0"),
            ("orders", "address_review_status", "VARCHAR(20) DEFAULT 'none'"),
            ("orders", "paid_at", "DATETIME"),
            ("orders", "store_reviewed_at", "DATETIME"),
            ("orders", "technician_wage_amount", "FLOAT DEFAULT 0"),
            ("orders", "commissionable_amount", "FLOAT DEFAULT 0"),
            ("orders", "rating", "INTEGER"),
            ("orders", "rating_remark", "TEXT"),
            ("orders", "created_by_user_id", "INTEGER REFERENCES users(id)"),
            ("orders", "proxy_creator_id", "INTEGER REFERENCES users(id)"),
            ("orders", "referrer_user_id", "INTEGER REFERENCES users(id)"),
            ("orders", "channel_manager_id_snapshot", "INTEGER REFERENCES users(id)"),
            ("orders", "is_proxy_order", "BOOLEAN DEFAULT 0"),
            ("orders", "proxy_reason", "VARCHAR(50)"),
            ("orders", "claim_status", "VARCHAR(20) DEFAULT 'not_required'"),
            ("orders", "claimed_by_user_id", "INTEGER REFERENCES users(id)"),
            ("orders", "claimed_at", "DATETIME"),
            ("orders", "customer_name_snapshot", "VARCHAR(50)"),
            ("orders", "customer_phone_snapshot", "VARCHAR(20)"),
            ("orders", "customer_address_snapshot", "VARCHAR(500)"),
            ("orders", "wage_mode", "VARCHAR(20) DEFAULT 'per_order'"),
            ("orders", "paid_amount", "FLOAT DEFAULT 0"),
            ("orders", "latest_payer_user_id", "INTEGER REFERENCES users(id)"),
            ("orders", "service_confirmation_method", "VARCHAR(30)"),
            ("orders", "service_confirmation_note", "TEXT"),
            ("orders", "service_confirmed_at", "DATETIME"),
            ("orders", "risk_review_required", "BOOLEAN DEFAULT 0"),
            ("orders", "settlement_status", "VARCHAR(20) DEFAULT 'pending'"),
            ("service_bills", "confirmation_method", "VARCHAR(30)"),
            ("service_bills", "confirmation_note", "TEXT"),
            ("service_bills", "confirmed_at", "DATETIME"),
            ("profit_shares", "store_id", "INTEGER REFERENCES stores(id)"),
            ("pay_orders", "out_trade_no", "VARCHAR(64)"),
            ("pay_orders", "prepay_id", "VARCHAR(128)"),
            ("pay_orders", "payer_openid", "VARCHAR(128)"),
            ("pay_orders", "notify_payload", "TEXT"),
            ("withdrawals", "payout_provider", "VARCHAR(20) DEFAULT 'manual'"),
            ("withdrawals", "payout_status", "VARCHAR(30) DEFAULT 'none'"),
            ("withdrawals", "transfer_out_bill_no", "VARCHAR(64)"),
            ("withdrawals", "transfer_bill_no", "VARCHAR(128)"),
            ("withdrawals", "transfer_payload", "TEXT"),
            ("withdrawals", "payout_at", "DATETIME"),
            ("store_addresses", "service_area_id", "INTEGER REFERENCES service_areas(id)"),
            ("store_addresses", "address_code", "VARCHAR(40)"),
            ("store_addresses", "canonical_key", "VARCHAR(64)"),
            ("store_addresses", "province", "VARCHAR(40) DEFAULT '福建省'"),
            ("store_addresses", "estate", "VARCHAR(160) DEFAULT ''"),
            ("store_addresses", "building", "VARCHAR(80) DEFAULT ''"),
            ("store_addresses", "unit", "VARCHAR(80) DEFAULT ''"),
            ("store_addresses", "room", "VARCHAR(80) DEFAULT ''"),
            ("store_addresses", "full_address", "VARCHAR(500)"),
            ("store_addresses", "business_owner_user_id", "INTEGER REFERENCES users(id)"),
            ("store_addresses", "created_by_user_id", "INTEGER REFERENCES users(id)"),
            ("customer_addresses", "service_address_id", "INTEGER REFERENCES store_addresses(id)"),
        ]
        for table, column, col_type in migrations:
            try:
                await conn.execute(text(f"SELECT {column} FROM {table} LIMIT 1"))
            except Exception:
                await conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                )

        await conn.execute(text("UPDATE orders SET source='REPAIR' WHERE source='repair'"))
        await conn.execute(text("UPDATE orders SET source='PACKAGE' WHERE source='package'"))
        await conn.execute(
            text("UPDATE orders SET source='AFTER_SALES' WHERE source='after_sales'")
        )

        # 2026-10-07 multi-role backfill:
        #   存量用户原来只有一个 business_role,迁移后把它灌进 business_roles,
        #   同时把 active_business_role 指向它 —— 这样老账号第一次进小程序
        #   就落在自己的工作台,不会掉回客户身份。
        #   `NOT IN ('[]','null','')` 保证只在空值时写入,可反复执行。
        try:
            await conn.execute(
                text(
                    "UPDATE users SET active_business_role = "
                    "CASE WHEN business_role IS NULL OR business_role = '' "
                    "THEN 'customer' ELSE business_role END "
                    "WHERE active_business_role IS NULL OR active_business_role = ''"
                )
            )
        except Exception:
            pass

        # business_roles 是 JSON 数组列,必须写成合法 JSON(如 ["store_manager"])。
        # `NOT LIKE '[%'` 保证只在空值/非数组值时回填,可反复执行。
        try:
            await conn.execute(
                text(
                    "UPDATE users SET business_roles = '[\"' || "
                    "CASE WHEN business_role IS NULL OR business_role = '' "
                    "THEN 'customer' ELSE business_role END || '\"]' "
                    "WHERE business_roles IS NULL OR business_roles = '' "
                    "OR business_roles = 'null' OR business_roles NOT LIKE '[%'"
                )
            )
        except Exception:
            pass

        await _create_optional_unique_index(
            conn,
            "uq_pay_orders_out_trade_no",
            "pay_orders",
            "out_trade_no",
            "out_trade_no IS NOT NULL",
        )
        await _create_optional_unique_index(
            conn,
            "uq_store_addresses_address_code",
            "store_addresses",
            "address_code",
            "address_code IS NOT NULL",
        )
        await _create_optional_unique_index(
            conn,
            "uq_store_addresses_canonical_key",
            "store_addresses",
            "canonical_key",
            "canonical_key IS NOT NULL",
        )
        await _create_optional_unique_index(
            conn,
            "uq_users_wechat_openid",
            "users",
            "wechat_openid",
            "wechat_openid IS NOT NULL",
        )
        await _create_optional_unique_index(
            conn,
            "uq_withdrawals_transfer_out_bill_no",
            "withdrawals",
            "transfer_out_bill_no",
            "transfer_out_bill_no IS NOT NULL",
        )

        await conn.commit()


async def _create_optional_unique_index(conn, index_name: str, table: str, column: str, predicate: str):
    try:
        if conn.dialect.name == "sqlite":
            await conn.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} "
                    f"ON {table}({column}) WHERE {predicate}"
                )
            )
        else:
            await conn.execute(
                text(f"CREATE UNIQUE INDEX {index_name} ON {table}({column})")
            )
    except Exception:
        pass
