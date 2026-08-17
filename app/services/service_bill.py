"""Service bill workflow."""

import json

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.order import Order, OrderStatus
from ..models.service_bill import ServiceBill, ServiceBillStatus
from ..schemas.service_bill import ServiceBillCreate
from .order import transition_status


async def submit_bill(db: AsyncSession, order: Order, data: ServiceBillCreate) -> ServiceBill:
    if order.status not in (
        OrderStatus.SERVICING,
        OrderStatus.BILL_RETURNED,
        OrderStatus.IN_PROGRESS,
    ):
        raise ValueError("Only servicing or returned orders can submit a service bill")

    try:
        items = json.loads(data.items_json)
    except Exception as exc:
        raise ValueError("Service bill items must be valid JSON") from exc
    if not isinstance(items, list) or not items or len(items) > 100:
        raise ValueError("Service bill must contain between 1 and 100 items")
    calculated = 0.0
    normalized = []
    for item in items:
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            raise ValueError("Every service item requires a name")
        quantity = float(item.get("quantity", item.get("qty", 0)) or 0)
        unit_price = float(item.get("unit_price", item.get("price", 0)) or 0)
        if quantity <= 0 or unit_price < 0:
            raise ValueError("Service item quantity and price are invalid")
        subtotal = round(quantity * unit_price, 2)
        provided = float(item.get("subtotal", item.get("amount", subtotal)) or 0)
        if abs(provided - subtotal) > 0.01:
            raise ValueError("Service item subtotal does not match quantity and unit price")
        calculated += subtotal
        normalized.append({
            "name": str(item["name"]).strip(),
            "quantity": quantity,
            "unit_price": unit_price,
            "subtotal": subtotal,
            "remark": item.get("remark"),
        })
    if abs(round(calculated, 2) - data.amount) > 0.01:
        raise ValueError("Service bill total does not match item subtotals")

    existing = await db.execute(
        select(ServiceBill)
        .where(ServiceBill.order_id == order.id)
        .order_by(ServiceBill.id.desc())
        .limit(1)
    )
    previous = existing.scalar_one_or_none()
    revision = (previous.revision + 1) if previous else 1

    bill = ServiceBill(
        order_id=order.id,
        repairer_id=data.repairer_id,
        title=data.title,
        items_json=json.dumps(normalized, ensure_ascii=False),
        amount=data.amount,
        warranty_days=data.warranty_days,
        media_json=data.media_json,
        revision=revision,
        status=ServiceBillStatus.SUBMITTED,
        confirmation_method=data.confirmation_method,
        confirmation_note=data.confirmation_note,
    )
    db.add(bill)
    order.price = data.amount
    order.assigned_repairer_id = order.assigned_repairer_id or data.repairer_id
    await db.flush()
    if data.save_as_draft:
        bill.status = ServiceBillStatus.DRAFT
        await db.commit()
        await db.refresh(bill)
        return bill
    order.service_confirmation_method = data.confirmation_method
    order.service_confirmation_note = data.confirmation_note
    order.service_confirmed_at = datetime.now(timezone.utc) if data.confirmation_method else None
    await transition_status(
        db,
        order,
        OrderStatus.WAIT_PAYMENT,
        operator_type="repairer",
        operator_id=data.repairer_id,
        remark=f"service bill submitted for payment #{revision}",
    )
    await db.refresh(bill)
    return bill


async def return_bill(
    db: AsyncSession, order: Order, bill: ServiceBill, reason: str | None
) -> ServiceBill:
    bill.status = ServiceBillStatus.RETURNED
    bill.return_reason = reason
    await transition_status(
        db,
        order,
        OrderStatus.BILL_RETURNED,
        operator_type="customer",
        remark=reason or "service bill returned",
    )
    await db.refresh(bill)
    return bill


async def confirm_bill(db: AsyncSession, order: Order, bill: ServiceBill) -> ServiceBill:
    bill.status = ServiceBillStatus.CONFIRMED
    bill.confirmed_at = datetime.now(timezone.utc)
    order.price = bill.amount
    if order.status != OrderStatus.WAIT_PAYMENT:
        await transition_status(
            db,
            order,
            OrderStatus.WAIT_PAYMENT,
            operator_type="customer",
            remark="service bill confirmed",
        )
    else:
        await db.commit()
    await db.refresh(bill)
    return bill


async def get_latest_bill(db: AsyncSession, order_id: int) -> ServiceBill | None:
    result = await db.execute(
        select(ServiceBill)
        .where(ServiceBill.order_id == order_id)
        .order_by(ServiceBill.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
