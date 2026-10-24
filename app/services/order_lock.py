"""Serialize price revision and payment against the same business order."""

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.order import Order


async def lock_order(db: AsyncSession, order_id: int) -> Order:
    # A no-op write also acquires a transaction write lock on SQLite, where
    # SELECT FOR UPDATE is ignored. Preserve the business updated_at value.
    result = await db.execute(
        update(Order).where(Order.id == order_id)
        .values(updated_at=Order.updated_at)
        .execution_options(synchronize_session=False)
    )
    if not result.rowcount:
        raise ValueError("Order not found")
    order = await db.get(Order, order_id, populate_existing=True)
    return order
