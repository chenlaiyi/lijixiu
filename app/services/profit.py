"""Revenue allocation for paid orders."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.order import Order
from ..models.profit_share import PROFIT_RATIOS, ProfitRole, ProfitShare, ProfitStatus
from ..models.store import Store
from ..models.user import BusinessRole, User


async def _find_channel_manager(db: AsyncSession, customer_id: int) -> int | None:
    customer = await db.get(User, customer_id)
    if not customer or not customer.promotion_manager_id:
        return None

    manager = await db.get(User, customer.promotion_manager_id)
    if manager and manager.is_promotion_manager:
        return manager.id
    return None


async def _find_business_role_user(db: AsyncSession, role: BusinessRole) -> int | None:
    return (
        await db.execute(
            select(User.id)
            .where(User.business_role == role.value)
            .order_by(User.id)
            .limit(1)
        )
    ).scalar_one_or_none()


async def calculate_and_save(db: AsyncSession, order: Order) -> list[ProfitShare]:
    """Allocate order revenue without auto-paying technician wages."""
    existing_result = await db.execute(
        select(ProfitShare).where(ProfitShare.order_id == order.id)
    )
    existing = list(existing_result.scalars().all())
    expected_roles = {
        ProfitRole.STORE_REVENUE,
        ProfitRole.STORE_MANAGER_COMMISSION,
        ProfitRole.CITY_MANAGER_COMMISSION,
        ProfitRole.CHANNEL_MANAGER_COMMISSION,
        ProfitRole.TECH_SUPPORT,
        ProfitRole.REFERRAL_REWARD,
        ProfitRole.PLATFORM_RETAINED,
    }
    if order.is_proxy_order:
        expected_roles.add(ProfitRole.PROXY_ASSIST_REWARD)
    if order.commissionable_amount and order.price > order.commissionable_amount:
        expected_roles.add(ProfitRole.PASS_THROUGH)
    if existing and expected_roles.issubset({item.role_type for item in existing}):
        return existing
    if existing and all(item.status == ProfitStatus.PENDING for item in existing):
        for item in existing:
            await db.delete(item)
        await db.flush()
    elif existing:
        return existing

    base_amount = order.commissionable_amount or order.price
    if base_amount <= 0:
        return []

    store = await db.get(Store, order.store_id) if order.store_id else None
    channel_manager_id = order.channel_manager_id_snapshot
    if not order.address_book_id and channel_manager_id is None:
        channel_manager_id = await _find_channel_manager(db, order.customer_id)
    tech_support_id = await _find_business_role_user(db, BusinessRole.TECH_SUPPORT)

    rows: list[tuple[ProfitRole, int | None, int | None, float]] = [
        (
            ProfitRole.STORE_REVENUE,
            store.manager_id if store else None,
            store.id if store else order.store_id,
            PROFIT_RATIOS[ProfitRole.STORE_REVENUE],
        ),
        (
            ProfitRole.STORE_MANAGER_COMMISSION,
            store.manager_id if store else None,
            store.id if store else order.store_id,
            PROFIT_RATIOS[ProfitRole.STORE_MANAGER_COMMISSION],
        ),
        (
            ProfitRole.CITY_MANAGER_COMMISSION,
            store.city_manager_id if store else None,
            store.id if store else order.store_id,
            PROFIT_RATIOS[ProfitRole.CITY_MANAGER_COMMISSION],
        ),
        (
            ProfitRole.CHANNEL_MANAGER_COMMISSION,
            channel_manager_id,
            store.id if store else order.store_id,
            PROFIT_RATIOS[ProfitRole.CHANNEL_MANAGER_COMMISSION],
        ),
        (
            ProfitRole.TECH_SUPPORT,
            tech_support_id,
            store.id if store else order.store_id,
            PROFIT_RATIOS[ProfitRole.TECH_SUPPORT],
        ),
        (
            ProfitRole.REFERRAL_REWARD,
            order.referrer_user_id,
            store.id if store else order.store_id,
            PROFIT_RATIOS[ProfitRole.REFERRAL_REWARD],
        ),
        (
            ProfitRole.PLATFORM_RETAINED,
            None,
            None,
            1.5 if order.is_proxy_order else PROFIT_RATIOS[ProfitRole.PLATFORM_RETAINED],
        ),
    ]
    if order.is_proxy_order:
        rows.insert(
            -1,
            (
                ProfitRole.PROXY_ASSIST_REWARD,
                order.proxy_creator_id,
                store.id if store else order.store_id,
                PROFIT_RATIOS[ProfitRole.PROXY_ASSIST_REWARD],
            ),
        )

    records: list[ProfitShare] = []
    for role, user_id, store_id, ratio in rows:
        record = ProfitShare(
            order_id=order.id,
            user_id=user_id,
            store_id=store_id,
            role_type=role,
            amount=round(base_amount * ratio / 100.0, 2),
            ratio=ratio,
            status=ProfitStatus.PENDING,
        )
        db.add(record)
        records.append(record)

    pass_through = round(order.price - base_amount, 2)
    if pass_through > 0:
        record = ProfitShare(
            order_id=order.id,
            user_id=store.manager_id if store else None,
            store_id=store.id if store else order.store_id,
            role_type=ProfitRole.PASS_THROUGH,
            amount=pass_through,
            ratio=0,
            status=ProfitStatus.PENDING,
        )
        db.add(record)
        records.append(record)

    allocated = round(sum(item.amount for item in records), 2)
    remainder = round(order.price - allocated, 2)
    if remainder:
        platform = next(
            (item for item in records if item.role_type == ProfitRole.PLATFORM_RETAINED),
            None,
        )
        if platform:
            platform.amount = round(platform.amount + remainder, 2)

    await db.commit()
    for record in records:
        await db.refresh(record)
    return records


async def apply_per_order_wage(
    db: AsyncSession,
    order: Order,
    employee_user_id: int,
    amount: float,
) -> list[ProfitShare]:
    """Carve a per-order wage out of the store's 85% share."""
    records = await calculate_and_save(db, order)
    wage = next((item for item in records if item.role_type == ProfitRole.TECHNICIAN_WAGE), None)
    store_revenue = next((item for item in records if item.role_type == ProfitRole.STORE_REVENUE), None)
    if not store_revenue:
        raise ValueError("Store revenue share is missing")
    base_amount = order.commissionable_amount or order.price
    if amount < 0 or amount > round(base_amount * 0.85, 2):
        raise ValueError("Technician wage must be within the store's 85% revenue")

    gross_store_revenue = round(base_amount * 0.85, 2)
    store_revenue.amount = round(gross_store_revenue - amount, 2)
    if wage:
        wage.amount = round(amount, 2)
        wage.ratio = round(amount / base_amount * 100, 4) if base_amount else 0
        wage.user_id = employee_user_id
    elif amount > 0:
        wage = ProfitShare(
            order_id=order.id,
            user_id=employee_user_id,
            store_id=order.store_id,
            role_type=ProfitRole.TECHNICIAN_WAGE,
            amount=round(amount, 2),
            ratio=round(amount / base_amount * 100, 4) if base_amount else 0,
            status=ProfitStatus.PENDING,
        )
        db.add(wage)
        records.append(wage)
    await db.commit()
    return records


async def mark_order_profits_settled(db: AsyncSession, order_id: int) -> int:
    result = await db.execute(
        select(ProfitShare).where(ProfitShare.order_id == order_id)
    )
    items = list(result.scalars().all())
    now = datetime.now(timezone.utc)
    for item in items:
        item.status = ProfitStatus.SETTLED
        item.settled_at = now
    await db.commit()
    return len(items)


async def get_order_profits(db: AsyncSession, order_id: int) -> list[ProfitShare]:
    result = await db.execute(
        select(ProfitShare)
        .where(ProfitShare.order_id == order_id)
        .order_by(ProfitShare.role_type)
    )
    return list(result.scalars().all())


async def get_user_profits(
    db: AsyncSession, user_id: int, skip: int = 0, limit: int = 50
) -> list[ProfitShare]:
    result = await db.execute(
        select(ProfitShare)
        .where(ProfitShare.user_id == user_id)
        .order_by(ProfitShare.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())
