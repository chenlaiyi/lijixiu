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
        Wallet,
        WageRecord,
        WarrantyCertificate,
        Withdrawal,
    )

    # Never reuse archived business IDs in newly created SQLite databases.
    if engine.dialect.name == "sqlite":
        for table in Base.metadata.tables.values():
            table.dialect_options["sqlite"]["autoincrement"] = True
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.connect() as conn:
        migrations = [
            ("users", "active_business_role", "VARCHAR(30)"),
            ("orders", "door_number", "VARCHAR(240)"),
            ("store_addresses", "door_number", "VARCHAR(240)"),
            ("users", "password_hash", "VARCHAR(256)"),
            ("users", "is_active", "BOOLEAN DEFAULT 1"),
            ("users", "auth_version", "INTEGER DEFAULT 0"),
            ("users", "extra_roles_json", "VARCHAR(256)"),
            ("orders", "assigned_repairer_id", "INTEGER REFERENCES repairers(id)"),
            ("orders", "assigned_at", "DATETIME"),
            ("regions", "manager_id", "INTEGER REFERENCES users(id)"),
            ("users", "referrer_user_id", "INTEGER REFERENCES users(id)"),
            ("users", "referral_code", "VARCHAR(32)"),
            ("users", "promotion_manager_id", "INTEGER REFERENCES users(id)"),
            ("users", "is_promotion_manager", "BOOLEAN DEFAULT 0"),
            ("users", "wechat_openid", "VARCHAR(128)"),
            ("users", "business_role", "VARCHAR(30) DEFAULT 'customer'"),
            ("orders", "store_id", "INTEGER REFERENCES stores(id)"),
            ("orders", "source", "VARCHAR(20) DEFAULT 'repair'"),
            ("orders", "estate", "VARCHAR(160)"),
            ("orders", "building", "VARCHAR(80)"),
            ("orders", "unit", "VARCHAR(80)"),
            ("orders", "room", "VARCHAR(80)"),
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
