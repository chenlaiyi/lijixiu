"""Payment and refund service."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.business import DomesticContract, DomesticPaymentStage
from ..models.idempotency import IdempotencyKey, make_key
from ..models.order import Order, OrderSource, OrderStatus
from ..models.pay_order import PayOrder, PayProvider, PayStatus
from ..models.profit_share import ProfitShare, ProfitStatus
from ..models.refund_order import RefundOrder, RefundStatus
from ..models.service_bill import ServiceBillStatus
from ..models.user import User
from ..models.wallet import Wallet
from ..models.ledger import Ledger, LedgerType
from ..schemas.payment import PayCreateRequest, RefundCreateRequest
from ..core.config import settings
from . import safety
from . import wechat_pay
from .order_lock import lock_order
from .payment_provider import PaymentIntent, get_provider

WECHAT_PREPAY_REUSE_WINDOW = timedelta(minutes=110)


def _coerce_enum(enum_cls, value: str):
    try:
        return enum_cls(value)
    except ValueError:
        try:
            return enum_cls[value.upper()]
        except KeyError as exc:
            raise ValueError(f"Unsupported {enum_cls.__name__}: {value}") from exc


def _as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _can_reuse_wechat_prepay(pay_order: PayOrder, payer_openid: str | None) -> bool:
    if pay_order.provider != PayProvider.WECHAT or not pay_order.prepay_id:
        return False
    if payer_openid and pay_order.payer_openid and payer_openid != pay_order.payer_openid:
        return False
    created_at = _as_aware_utc(pay_order.created_at)
    if created_at is None:
        return False
    return datetime.now(timezone.utc) - created_at < WECHAT_PREPAY_REUSE_WINDOW


async def create_payment(db: AsyncSession, data: PayCreateRequest) -> PayOrder:
    if data.provider == PayProvider.ALIPAY:
        raise ValueError("Alipay is not integrated")
    if data.provider == PayProvider.MOCK and not settings.PAYMENT_ALLOW_MOCK:
        raise ValueError("模拟支付已关闭，请使用微信支付")
    order = await lock_order(db, data.order_id)
    if order.status == OrderStatus.BILL_SUBMITTED:
        from .service_bill import confirm_bill, get_latest_bill

        bill = await get_latest_bill(db, order.id)
        if not bill:
            raise ValueError("Service bill not found")
        await confirm_bill(db, order, bill)
        order = await lock_order(db, order.id)
    if order.status != OrderStatus.WAIT_PAYMENT:
        raise ValueError(f"Order status is {order.status.value}, expected wait_payment")
    payer = await db.get(User, data.user_id)
    if not payer:
        raise ValueError("Payer not found")
    outstanding = round(order.price - (order.paid_amount or 0), 2)
    is_installment = order.source in (OrderSource.MATERNITY, OrderSource.NANNY)
    if data.amount - outstanding > 0.01:
        raise ValueError(f"Payment exceeds outstanding amount: outstanding={outstanding}")
    if not is_installment and abs(outstanding - data.amount) > 0.01:
        raise ValueError(f"Payment amount mismatch: outstanding={outstanding}, payment={data.amount}")

    existing_result = await db.execute(
        select(PayOrder)
        .where(
            PayOrder.order_id == data.order_id,
            PayOrder.user_id == data.user_id,
            PayOrder.provider == data.provider,
            PayOrder.status == PayStatus.PENDING,
        )
        .order_by(PayOrder.id.desc())
        .limit(1)
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        if abs(existing.amount - data.amount) >= 0.005:
            raise ValueError("支付金额已更新，请重新获取支付信息")
        prepay_expired = (
            existing.provider == PayProvider.WECHAT
            and existing.prepay_id
            and not _can_reuse_wechat_prepay(existing, None)
        )
        if prepay_expired:
            existing.status = PayStatus.FAILED
            await db.commit()
        else:
            if not existing.out_trade_no:
                existing.out_trade_no = f"XJLJ{existing.id:010d}"
                await db.commit()
                await db.refresh(existing)
            return existing

    pay_order = PayOrder(
        order_id=data.order_id,
        user_id=data.user_id,
        amount=data.amount,
        status=PayStatus.PENDING,
        provider=data.provider,
    )
    db.add(pay_order)
    await db.commit()
    await db.refresh(pay_order)
    if not pay_order.out_trade_no:
        pay_order.out_trade_no = f"XJLJ{pay_order.id:010d}"
        await db.commit()
        await db.refresh(pay_order)
    return pay_order


async def create_payment_intent(
    db: AsyncSession,
    pay_order: PayOrder,
    data: PayCreateRequest,
) -> PaymentIntent:
    order = await lock_order(db, pay_order.order_id)
    await db.refresh(pay_order)
    if (pay_order.status != PayStatus.PENDING or order.status != OrderStatus.WAIT_PAYMENT
            or abs(pay_order.amount - (order.price - (order.paid_amount or 0))) > 0.01
            and order.source not in (OrderSource.MATERNITY, OrderSource.NANNY)):
        raise ValueError("订单价格或支付状态已更新，请刷新后支付")
    try:
        payer_openid = data.payer_openid
        if pay_order.provider == PayProvider.WECHAT and data.js_code:
            payer_openid = wechat_pay.exchange_js_code(data.js_code)
            payer = await db.get(User, pay_order.user_id)
            if payer and payer.wechat_openid and payer.wechat_openid != payer_openid:
                raise ValueError("WeChat login does not match the paying user")
            if pay_order.prepay_id and pay_order.payer_openid != payer_openid:
                raise ValueError("Pending WeChat payment belongs to a different payer")

        if _can_reuse_wechat_prepay(pay_order, payer_openid):
            return PaymentIntent(
                pay_url=f"wechat://pay/{pay_order.id}",
                payment_params=wechat_pay.build_jsapi_payment_params(pay_order.prepay_id),
                prepay_id=pay_order.prepay_id,
                payer_openid=pay_order.payer_openid,
            )

        provider = get_provider(pay_order.provider.value)
        intent = await provider.create_payment(
            pay_order,
            payer_openid=payer_openid,
            js_code=None if payer_openid else data.js_code,
        )
    except Exception as exc:
        if pay_order.status == PayStatus.PENDING and not pay_order.prepay_id:
            pay_order.status = PayStatus.FAILED
            pay_order.notify_payload = json.dumps(
                {
                    "stage": "create_payment_intent",
                    "error": str(exc)[:500],
                },
                ensure_ascii=False,
            )
            await db.commit()
        raise
    changed = False
    if intent.prepay_id and pay_order.prepay_id != intent.prepay_id:
        pay_order.prepay_id = intent.prepay_id
        changed = True
    if intent.payer_openid and pay_order.payer_openid != intent.payer_openid:
        pay_order.payer_openid = intent.payer_openid
        changed = True
    if changed:
        await db.commit()
        await db.refresh(pay_order)
    return intent


async def handle_callback(
    db: AsyncSession,
    pay_order_id: int,
    transaction_id: str | None = None,
) -> PayOrder:
    key = make_key("payment_callback", pay_order_id)
    ok, existing = await safety.acquire_idempotency_key(db, key)
    if not ok:
        if existing and existing.status == "done":
            pay_order = await db.get(PayOrder, pay_order_id)
            if pay_order:
                return pay_order
        raise safety.SafetyError(f"Payment callback is already processing: {key}")

    pay_order = await db.get(PayOrder, pay_order_id)
    if not pay_order:
        raise ValueError(f"Pay order not found: #{pay_order_id}")
    if pay_order.provider != PayProvider.MOCK or not settings.PAYMENT_ALLOW_MOCK:
        raise ValueError("Manual callback is available only for mock payments")
    if pay_order.status == PayStatus.PAID:
        await _mark_idempotency_done(db, key)
        return pay_order

    provider = get_provider(pay_order.provider.value)
    result = await provider.verify_callback(pay_order, transaction_id)
    if not result.success:
        pay_order.status = PayStatus.FAILED
        await db.commit()
        raise ValueError(f"Payment verification failed: {result.message}")

    paid = await mark_payment_paid(
        db,
        pay_order,
        transaction_id=result.transaction_id,
        remark=f"payment callback: pay_order#{pay_order.id}",
    )
    await _mark_idempotency_done(db, key)
    return paid


async def _mark_idempotency_done(db: AsyncSession, key: str) -> None:
    result = await db.execute(select(IdempotencyKey).where(IdempotencyKey.key == key))
    ikey = result.scalar_one_or_none()
    if ikey:
        await safety.mark_idempotency_done(db, ikey)


async def mark_payment_paid(
    db: AsyncSession,
    pay_order: PayOrder,
    transaction_id: str | None,
    remark: str,
    notify_payload: dict | None = None,
) -> PayOrder:
    order = await lock_order(db, pay_order.order_id)
    await db.refresh(pay_order)
    if pay_order.status == PayStatus.PAID:
        return pay_order
    if pay_order.status == PayStatus.FAILED and pay_order.notify_payload:
        if json.loads(pay_order.notify_payload).get("stage") == "service_bill_revision":
            raise ValueError("此支付单已因服务单修改而关闭")

    if order.status != OrderStatus.WAIT_PAYMENT:
        raise ValueError("当前订单状态不能确认支付")

    pay_order.status = PayStatus.PAID
    pay_order.paid_at = datetime.now(timezone.utc)
    pay_order.transaction_id = transaction_id
    if notify_payload is not None:
        pay_order.notify_payload = json.dumps(notify_payload, ensure_ascii=False)

    order.paid_amount = round((order.paid_amount or 0) + pay_order.amount, 2)
    order.latest_payer_user_id = pay_order.user_id

    stage = (
        await db.execute(
            select(DomesticPaymentStage).where(DomesticPaymentStage.pay_order_id == pay_order.id)
        )
    ).scalar_one_or_none()
    if stage:
        stage.status = "paid"
        stage.payer_user_id = pay_order.user_id
        stage.paid_at = pay_order.paid_at

    fully_paid = order.paid_amount + 0.01 >= order.price
    if not fully_paid:
        await db.commit()
        contract = (
            await db.execute(select(DomesticContract).where(DomesticContract.order_id == order.id))
        ).scalar_one_or_none()
        if contract:
            contract.status = "in_service" if order.paid_amount > 0 else contract.status
            await db.commit()
        await db.refresh(pay_order)
        return pay_order

    from .order import transition_status
    from .service_bill import get_latest_bill

    bill = await get_latest_bill(db, order.id)
    if bill and bill.status.value != "confirmed":
        bill.status = ServiceBillStatus.CONFIRMED
        bill.confirmed_at = datetime.now(timezone.utc)

    await transition_status(
        db,
        order,
        OrderStatus.PAID,
        operator_type="system",
        remark=remark,
    )
    await db.refresh(order)
    await transition_status(
        db,
        order,
        OrderStatus.PAID_PENDING_REVIEW,
        operator_type="system",
        remark="payment completed, waiting for store review",
    )

    contract = (
        await db.execute(select(DomesticContract).where(DomesticContract.order_id == order.id))
    ).scalar_one_or_none()
    if contract:
        contract.status = "paid"
        await db.commit()

    await db.refresh(pay_order)
    return pay_order


def _cents(amount: float) -> int:
    return int(Decimal(str(amount)) * 100)


def _validate_wechat_payment(pay_order: PayOrder, payload: dict) -> None:
    if payload.get("out_trade_no") != pay_order.out_trade_no:
        raise ValueError("WeChat payment order number mismatch")
    if payload.get("appid") != settings.WECHAT_PAY_APPID or payload.get("mchid") != wechat_pay.mch_id():
        raise ValueError("WeChat payment merchant identity mismatch")
    if not payload.get("transaction_id"):
        raise ValueError("WeChat payment transaction_id missing")
    if pay_order.transaction_id and payload["transaction_id"] != pay_order.transaction_id:
        raise ValueError("WeChat payment transaction_id mismatch")
    amount = payload.get("amount") or {}
    if amount.get("total") != _cents(pay_order.amount):
        raise ValueError("WeChat payment amount mismatch")
    if amount.get("currency", "CNY") != "CNY":
        raise ValueError("WeChat payment currency mismatch")
    payer = payload.get("payer") or {}
    if pay_order.payer_openid and payer.get("openid") != pay_order.payer_openid:
        raise ValueError("WeChat payment payer mismatch")


async def handle_wechat_notification(
    db: AsyncSession,
    headers: dict[str, str],
    body: str,
) -> PayOrder:
    payload = wechat_pay.parse_notification(headers, body)
    out_trade_no = payload.get("out_trade_no")
    if not out_trade_no:
        raise ValueError("WeChat payment notify missing out_trade_no")

    result = await db.execute(select(PayOrder).where(PayOrder.out_trade_no == out_trade_no))
    pay_order = result.scalar_one_or_none()
    if not pay_order:
        raise ValueError(f"Pay order not found by out_trade_no: {out_trade_no}")
    if payload.get("appid") != settings.WECHAT_PAY_APPID or payload.get("mchid") != wechat_pay.mch_id():
        raise ValueError("WeChat payment merchant identity mismatch")

    trade_state = payload.get("trade_state")
    if trade_state != "SUCCESS":
        pay_order.notify_payload = json.dumps(payload, ensure_ascii=False)
        if pay_order.status == PayStatus.PENDING and trade_state in {"CLOSED", "REVOKED", "PAYERROR"}:
            pay_order.status = PayStatus.FAILED
        await db.commit()
        return pay_order

    _validate_wechat_payment(pay_order, payload)
    return await mark_payment_paid(
        db,
        pay_order,
        transaction_id=payload.get("transaction_id"),
        remark=f"wechat payment notify: {out_trade_no}",
        notify_payload=payload,
    )


async def sync_wechat_payment(db: AsyncSession, pay_order_id: int) -> PayOrder:
    pay_order = await db.get(PayOrder, pay_order_id)
    if not pay_order:
        raise ValueError(f"Pay order not found: #{pay_order_id}")
    if pay_order.provider != PayProvider.WECHAT:
        raise ValueError("Only WeChat payment can be synced")
    if not pay_order.out_trade_no:
        raise ValueError("Pay order missing out_trade_no")
    if pay_order.status in {PayStatus.PAID, PayStatus.PARTIALLY_REFUNDED, PayStatus.REFUNDED}:
        return pay_order

    payload = wechat_pay.query_transaction(pay_order.out_trade_no)
    trade_state = payload.get("trade_state")
    pay_order.notify_payload = json.dumps(payload, ensure_ascii=False)
    if trade_state == "SUCCESS":
        _validate_wechat_payment(pay_order, payload)
        return await mark_payment_paid(
            db,
            pay_order,
            transaction_id=payload.get("transaction_id"),
            remark=f"wechat payment query sync: {pay_order.out_trade_no}",
            notify_payload=payload,
        )
    if trade_state in {"CLOSED", "REVOKED", "PAYERROR"}:
        pay_order.status = PayStatus.FAILED
    await db.commit()
    await db.refresh(pay_order)
    return pay_order


async def _refunded_or_processing_amount(db: AsyncSession, pay_order_id: int) -> float:
    amount = (
        await db.execute(
            select(func.coalesce(func.sum(RefundOrder.amount), 0.0)).where(
                RefundOrder.pay_order_id == pay_order_id,
                RefundOrder.status.in_([RefundStatus.PROCESSING, RefundStatus.SUCCESS]),
            )
        )
    ).scalar()
    return float(amount or 0)


def _refund_status(value: str | None) -> RefundStatus:
    normalized = str(value or "PROCESSING").lower()
    if normalized == "success":
        return RefundStatus.SUCCESS
    if normalized in {"closed", "close"}:
        return RefundStatus.CLOSED
    if normalized in {"abnormal", "failed", "failure"}:
        return RefundStatus.FAILED
    return RefundStatus.PROCESSING


async def _validate_wechat_refund(db: AsyncSession, refund: RefundOrder, payload: dict) -> None:
    pay_order = await db.get(PayOrder, refund.pay_order_id)
    if not pay_order:
        raise ValueError("Refund payment not found")
    if payload.get("out_refund_no") != refund.out_refund_no:
        raise ValueError("WeChat refund number mismatch")
    if payload.get("out_trade_no") != pay_order.out_trade_no:
        raise ValueError("WeChat refund payment number mismatch")
    if payload.get("mchid") and payload["mchid"] != wechat_pay.mch_id():
        raise ValueError("WeChat refund merchant mismatch")
    if pay_order.transaction_id and payload.get("transaction_id") != pay_order.transaction_id:
        raise ValueError("WeChat refund transaction mismatch")
    amount = payload.get("amount") or {}
    if amount.get("refund") != _cents(refund.amount) or amount.get("total") != _cents(pay_order.amount):
        raise ValueError("WeChat refund amount mismatch")
    if not (payload.get("status") or payload.get("refund_status")):
        raise ValueError("WeChat refund status missing")


async def _apply_refund_payload(
    db: AsyncSession,
    refund: RefundOrder,
    payload: dict,
) -> RefundOrder:
    refund = (await db.execute(
        select(RefundOrder).where(RefundOrder.id == refund.id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    await _validate_wechat_refund(db, refund, payload)
    status = _refund_status(payload.get("status") or payload.get("refund_status"))
    if refund.status == RefundStatus.SUCCESS and status != RefundStatus.SUCCESS:
        return refund
    refund.status = status
    refund.refund_id = payload.get("refund_id") or refund.refund_id
    refund.notify_payload = json.dumps(payload, ensure_ascii=False)
    first_success = status == RefundStatus.SUCCESS and refund.success_at is None
    if first_success:
        refund.success_at = datetime.now(timezone.utc)
    if status == RefundStatus.SUCCESS:
        await _apply_refund_clawback(db, refund, first_success=first_success)
    await db.commit()
    await db.refresh(refund)
    await _refresh_payment_refund_status(db, refund.pay_order_id)
    if status == RefundStatus.SUCCESS:
        pay_order = await db.get(PayOrder, refund.pay_order_id)
        if pay_order and pay_order.status == PayStatus.REFUNDED:
            stage = (await db.execute(
                select(DomesticPaymentStage).where(DomesticPaymentStage.pay_order_id == pay_order.id)
            )).scalar_one_or_none()
            if stage and stage.status != "refunded":
                stage.status = "refunded"
                await db.commit()
    return refund


async def _apply_refund_clawback(db: AsyncSession, refund: RefundOrder, *, first_success: bool) -> None:
    order = (await db.execute(
        select(Order).where(Order.id == refund.order_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    pay_order = await db.get(PayOrder, refund.pay_order_id)
    if not order or not pay_order:
        return
    if first_success:
        order.paid_amount = max(0.0, round((order.paid_amount or 0) - refund.amount, 2))

    shares = list((await db.execute(
        select(ProfitShare).where(
            ProfitShare.order_id == order.id,
            ProfitShare.status == ProfitStatus.SETTLED,
            ProfitShare.user_id.is_not(None),
        )
    )).scalars().all())
    ratio = min(1.0, refund.amount / order.price) if order.price > 0 else 0
    debits: dict[int, float] = {}
    for share in shares:
        share_debit = round(share.amount * ratio, 2)
        debits[share.user_id] = round(debits.get(share.user_id, 0) + share_debit, 2)
    existing_debits = set((await db.execute(
        select(Ledger.user_id).where(
            Ledger.reference_type == "refund_order",
            Ledger.reference_id == refund.id,
            Ledger.type == LedgerType.REFUND_CLAWBACK,
        )
    )).scalars().all())
    pending = {user_id: amount for user_id, amount in debits.items()
               if amount > 0 and user_id not in existing_debits}
    for user_id, amount in pending.items():
        wallet = (
            await db.execute(select(Wallet).where(Wallet.user_id == user_id))
        ).scalar_one_or_none()
        if not wallet or wallet.available_balance + 0.01 < amount:
            order.risk_review_required = True
            order.settlement_status = "clawback_required"
            await db.commit()
            return
    for user_id, amount in pending.items():
        await safety.safe_debit(
            db,
            user_id,
            amount,
            LedgerType.REFUND_CLAWBACK,
            ref_type="refund_order",
            ref_id=refund.id,
            remark=f"订单#{order.id}退款收益追回",
        )
    order.settlement_status = "refunded" if order.paid_amount <= 0 else "partially_refunded"
    await db.commit()


async def _refresh_payment_refund_status(db: AsyncSession, pay_order_id: int) -> None:
    pay_order = await db.get(PayOrder, pay_order_id)
    if not pay_order:
        return
    refunded = (
        await db.execute(
            select(func.coalesce(func.sum(RefundOrder.amount), 0.0)).where(
                RefundOrder.pay_order_id == pay_order_id,
                RefundOrder.status == RefundStatus.SUCCESS,
            )
        )
    ).scalar() or 0.0
    refunded = float(refunded)
    if refunded <= 0:
        return
    if refunded + 0.01 >= float(pay_order.amount):
        pay_order.status = PayStatus.REFUNDED
    else:
        pay_order.status = PayStatus.PARTIALLY_REFUNDED
    await db.commit()
    total_paid = float((await db.execute(
        select(func.coalesce(func.sum(PayOrder.amount), 0.0)).where(
            PayOrder.order_id == pay_order.order_id,
            PayOrder.status.in_([
                PayStatus.PAID,
                PayStatus.PARTIALLY_REFUNDED,
                PayStatus.REFUNDED,
            ]),
        )
    )).scalar() or 0.0)
    total_refunded = float((await db.execute(
        select(func.coalesce(func.sum(RefundOrder.amount), 0.0)).where(
            RefundOrder.order_id == pay_order.order_id,
            RefundOrder.status == RefundStatus.SUCCESS,
        )
    )).scalar() or 0.0)
    if total_paid > 0 and total_refunded + 0.01 >= total_paid:
        await _mark_order_refunded(db, pay_order.order_id)


async def _mark_order_refunding(db: AsyncSession, order_id: int) -> None:
    order = await db.get(Order, order_id)
    if not order or order.status in {OrderStatus.REFUNDING, OrderStatus.REFUNDED}:
        return
    from .order import transition_status

    try:
        await transition_status(db, order, OrderStatus.REFUNDING, operator_type="admin", remark="refund requested")
    except ValueError:
        order.status = OrderStatus.REFUNDING
        await db.commit()


async def _mark_order_refunded(db: AsyncSession, order_id: int) -> None:
    order = await db.get(Order, order_id)
    if not order or order.status == OrderStatus.REFUNDED:
        return
    from .order import transition_status

    try:
        await transition_status(db, order, OrderStatus.REFUNDED, operator_type="system", remark="refund completed")
    except ValueError:
        order.status = OrderStatus.REFUNDED
        await db.commit()


async def _find_refundable_pay_order(
    db: AsyncSession, data: RefundCreateRequest
) -> PayOrder:
    if data.pay_order_id:
        pay_order = await db.get(PayOrder, data.pay_order_id)
        if not pay_order:
            raise ValueError("Pay order not found")
        return pay_order
    if not data.order_id:
        raise ValueError("pay_order_id or order_id is required")
    result = await db.execute(
        select(PayOrder)
        .where(
            PayOrder.order_id == data.order_id,
            PayOrder.provider == PayProvider.WECHAT,
            PayOrder.status.in_([PayStatus.PAID, PayStatus.PARTIALLY_REFUNDED]),
        )
        .order_by(PayOrder.id.desc())
        .limit(1)
    )
    pay_order = result.scalar_one_or_none()
    if not pay_order:
        raise ValueError("No refundable WeChat pay order found")
    return pay_order


async def create_refund(db: AsyncSession, data: RefundCreateRequest) -> RefundOrder:
    pay_order = await _find_refundable_pay_order(db, data)
    pay_order = (await db.execute(
        select(PayOrder).where(PayOrder.id == pay_order.id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    if pay_order.provider != PayProvider.WECHAT:
        raise ValueError("Only WeChat payments can be refunded")
    if pay_order.status not in (PayStatus.PAID, PayStatus.PARTIALLY_REFUNDED):
        raise ValueError(f"Pay order status is {pay_order.status.value}, expected paid")
    if not pay_order.out_trade_no:
        raise ValueError("Pay order missing out_trade_no")

    locked_amount = await _refunded_or_processing_amount(db, pay_order.id)
    refundable = float(pay_order.amount) - locked_amount
    if data.amount > refundable + 0.01:
        raise ValueError(f"Refund amount exceeds refundable balance: {refundable:.2f}")

    refund = RefundOrder(
        pay_order_id=pay_order.id,
        order_id=pay_order.order_id,
        user_id=pay_order.user_id,
        amount=data.amount,
        reason=data.reason,
        status=RefundStatus.PROCESSING,
        operator_id=data.operator_id,
    )
    db.add(refund)
    await db.commit()
    await db.refresh(refund)
    refund.out_refund_no = f"XJTK{refund.id:010d}"
    await db.commit()
    await db.refresh(refund)

    try:
        result = wechat_pay.create_refund(pay_order, refund.out_refund_no, refund.amount, refund.reason)
    except wechat_pay.WeChatPayError as exc:
        # An HTTP failure may happen after WeChat accepts the request. Keep the
        # refund reserved until a query establishes its final state.
        refund.notify_payload = json.dumps({"submit_error": str(exc)[:500]}, ensure_ascii=False)
        await db.commit()
        try:
            payload = wechat_pay.query_refund(refund.out_refund_no)
        except wechat_pay.WeChatPayError:
            raise wechat_pay.WeChatPayError("Refund result unknown; sync this refund before retrying") from exc
        await _apply_refund_payload(db, refund, payload)
        return refund

    await _apply_refund_payload(db, refund, result.payload)
    if refund.status == RefundStatus.PROCESSING and data.amount + 0.01 >= pay_order.amount:
        await _mark_order_refunding(db, pay_order.order_id)
    await db.refresh(refund)
    return refund


async def handle_wechat_refund_notification(
    db: AsyncSession,
    headers: dict[str, str],
    body: str,
) -> RefundOrder:
    payload = wechat_pay.parse_notification(headers, body)
    out_refund_no = payload.get("out_refund_no")
    if not out_refund_no:
        raise ValueError("WeChat refund notify missing out_refund_no")
    result = await db.execute(select(RefundOrder).where(RefundOrder.out_refund_no == out_refund_no))
    refund = result.scalar_one_or_none()
    if not refund:
        raise ValueError(f"Refund order not found: {out_refund_no}")
    return await _apply_refund_payload(db, refund, payload)


async def sync_wechat_refund(db: AsyncSession, refund_order_id: int) -> RefundOrder:
    refund = await db.get(RefundOrder, refund_order_id)
    if not refund:
        raise ValueError(f"Refund order not found: #{refund_order_id}")
    if not refund.out_refund_no:
        raise ValueError("Refund order missing out_refund_no")
    payload = wechat_pay.query_refund(refund.out_refund_no)
    return await _apply_refund_payload(db, refund, payload)


async def get_pay_order(db: AsyncSession, pay_order_id: int) -> PayOrder | None:
    return await db.get(PayOrder, pay_order_id)


async def list_pay_orders(
    db: AsyncSession,
    order_id: int | None = None,
    user_id: int | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> list[PayOrder]:
    stmt = select(PayOrder)
    if order_id:
        stmt = stmt.where(PayOrder.order_id == order_id)
    if user_id:
        stmt = stmt.where(PayOrder.user_id == user_id)
    if status:
        stmt = stmt.where(PayOrder.status == _coerce_enum(PayStatus, status))
    stmt = stmt.order_by(PayOrder.id.desc()).offset(skip).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def list_refunds(
    db: AsyncSession,
    pay_order_id: int | None = None,
    order_id: int | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> list[RefundOrder]:
    stmt = select(RefundOrder)
    if pay_order_id:
        stmt = stmt.where(RefundOrder.pay_order_id == pay_order_id)
    if order_id:
        stmt = stmt.where(RefundOrder.order_id == order_id)
    if status:
        stmt = stmt.where(RefundOrder.status == _coerce_enum(RefundStatus, status))
    stmt = stmt.order_by(RefundOrder.id.desc()).offset(skip).limit(limit)
    return list((await db.execute(stmt)).scalars().all())
