"""Service bill workflow."""

import json
import math

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.order import Order, OrderStatus
from ..models.service_bill import ServiceBill, ServiceBillStatus
from ..models.pay_order import PayOrder, PayProvider, PayStatus
from ..schemas.service_bill import ServiceBillCreate
from .order import transition_status, write_log
from .order_lock import lock_order
from . import wechat_pay


async def submit_bill(db: AsyncSession, order: Order, data: ServiceBillCreate) -> ServiceBill:
    order = await lock_order(db, order.id)
    revising = order.status in (OrderStatus.WAIT_PAYMENT, OrderStatus.BILL_SUBMITTED)
    if order.status not in (
        OrderStatus.SERVICING,
        OrderStatus.BILL_RETURNED,
        OrderStatus.IN_PROGRESS,
        OrderStatus.WAIT_PAYMENT,
        OrderStatus.BILL_SUBMITTED,
    ):
        raise ValueError("Only servicing or returned orders can submit a service bill")
    if (order.paid_amount or 0) > 0:
        raise ValueError("客户已付款，不能修改服务单")
    if data.repairer_id != (order.repairer_id or order.assigned_repairer_id):
        raise ValueError("仅本单服务师傅可以提交服务单")
    if revising and data.save_as_draft:
        raise ValueError("已提交的服务单请修改后重新提交，不支持保存草稿")

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
        if not all(math.isfinite(v) for v in (quantity, unit_price)) or quantity <= 0 or unit_price < 0:
            raise ValueError("Service item quantity and price are invalid")
        subtotal = round(quantity * unit_price, 2)
        provided = float(item.get("subtotal", item.get("amount", subtotal)) or 0)
        if not math.isfinite(provided) or abs(provided - subtotal) > 0.01:
            raise ValueError("Service item subtotal does not match quantity and unit price")
        calculated += subtotal
        normalized.append({
            "name": str(item["name"]).strip(),
            "quantity": quantity,
            "unit_price": unit_price,
            "subtotal": subtotal,
            "remark": item.get("remark"),
        })
    if not math.isfinite(data.amount) or not math.isfinite(calculated) or abs(round(calculated, 2) - data.amount) > 0.01:
        raise ValueError("Service bill total does not match item subtotals")

    existing = await db.execute(
        select(ServiceBill)
        .where(ServiceBill.order_id == order.id)
        .order_by(ServiceBill.id.desc())
        .limit(1)
    )
    previous = existing.scalar_one_or_none()
    if revising and (not previous or data.expected_revision != previous.revision):
        raise ValueError("服务单已更新，请刷新后重新修改")
    revision = (previous.revision + 1) if previous else 1

    if not data.save_as_draft:
        payments = list((await db.execute(select(PayOrder).where(PayOrder.order_id == order.id))).scalars())
        if any(p.status in (PayStatus.PAID, PayStatus.PARTIALLY_REFUNDED, PayStatus.REFUNDED) for p in payments):
            raise ValueError("客户已有支付记录，不能修改服务单")
        for payment in payments:
            # FAILED can still carry a prepay id after a transient callback error.
            if payment.status not in (PayStatus.PENDING, PayStatus.FAILED):
                continue
            if payment.provider == PayProvider.WECHAT and payment.prepay_id:
                try:
                    state = wechat_pay.query_transaction(payment.out_trade_no).get("trade_state")
                    if state in ("NOTPAY", "USERPAYING"):
                        wechat_pay.close_transaction(payment.out_trade_no)
                    elif state not in ("CLOSED", "REVOKED", "PAYERROR"):
                        raise ValueError("支付已成功或正在处理，请先刷新支付状态")
                except wechat_pay.WeChatPayError as exc:
                    raise ValueError("旧支付单未能关闭，请稍后重试修改") from exc
            payment.status = PayStatus.FAILED
            payment.notify_payload = json.dumps({"stage": "service_bill_revision", "revision": revision})

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
    order.assigned_repairer_id = order.assigned_repairer_id or data.repairer_id
    await db.flush()
    if data.save_as_draft:
        bill.status = ServiceBillStatus.DRAFT
        await db.commit()
        await db.refresh(bill)
        return bill
    old_price = order.price
    order.price = data.amount
    order.service_confirmation_method = data.confirmation_method
    order.service_confirmation_note = data.confirmation_note
    order.service_confirmed_at = datetime.now(timezone.utc) if data.confirmation_method else None
    if revising:
        await write_log(db, order, order.status.value, OrderStatus.WAIT_PAYMENT.value,
                        operator_type="repairer", operator_id=data.repairer_id,
                        remark=f"service bill revised #{revision}: {old_price:.2f} -> {data.amount:.2f}")
        order.status = OrderStatus.WAIT_PAYMENT
        await db.commit()
    else:
        if order.status == OrderStatus.BILL_RETURNED:
            await transition_status(db, order, OrderStatus.BILL_SUBMITTED,
                                    operator_type="repairer", operator_id=data.repairer_id)
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
    order = await lock_order(db, order.id)
    latest = await get_latest_bill(db, order.id)
    if not latest or latest.id != bill.id or bill.status == ServiceBillStatus.DRAFT:
        raise ValueError("服务单已更新，请刷新")
    if order.status not in (OrderStatus.BILL_SUBMITTED, OrderStatus.WAIT_PAYMENT) or (order.paid_amount or 0) > 0:
        raise ValueError("当前订单不能确认服务单")
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
