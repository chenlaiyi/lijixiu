"""Wallet and withdrawal services."""

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models.idempotency import KEY_WITHDRAW, KEY_WITHDRAW_REVIEW, make_key
from ..models.ledger import Ledger, LedgerType
from ..models.profit_share import ProfitStatus
from ..models.user import User
from ..models.wallet import Wallet
from ..models.withdrawal import Withdrawal, WithdrawalStatus
from . import safety
from . import wechat_pay

TRANSFER_SUCCESS_STATES = {"success"}
TRANSFER_PROCESSING_STATES = {"accepted", "processing", "wait_user_confirm", "waiting", "pending"}
TRANSFER_FAIL_STATES = {"failed", "fail", "closed", "cancelled", "cancel", "timeout"}


def _coerce_withdrawal_status(status: str) -> WithdrawalStatus:
    try:
        return WithdrawalStatus(status)
    except ValueError:
        try:
            return WithdrawalStatus[status.upper()]
        except KeyError as exc:
            raise ValueError(f"Unsupported withdrawal status: {status}") from exc


async def get_wallet(db: AsyncSession, user_id: int) -> Wallet | None:
    result = await db.execute(select(Wallet).where(Wallet.user_id == user_id))
    return result.scalar_one_or_none()


async def get_or_create_wallet(db: AsyncSession, user_id: int) -> Wallet:
    wallet = await get_wallet(db, user_id)
    if wallet:
        return wallet
    wallet = Wallet(user_id=user_id)
    db.add(wallet)
    await db.commit()
    await db.refresh(wallet)
    return wallet


async def settle_profit_shares(db: AsyncSession, profit_records) -> int:
    if not profit_records:
        return 0

    order_id = profit_records[0].order_id
    key = make_key("profit_settle", order_id)
    ok, existing = await safety.acquire_idempotency_key(db, key)
    if not ok:
        if existing and existing.status == "done":
            return 0
        raise safety.SafetyError(f"profit settlement already processing: {key}")

    settled_count = 0
    try:
        for ps in profit_records:
            if ps.user_id is not None and ps.amount > 0:
                ledger_type = (
                    LedgerType.TECHNICIAN_WAGE
                    if ps.role_type.value == "technician_wage"
                    else LedgerType.PROFIT_SETTLEMENT
                )
                await safety.safe_deposit(
                    db,
                    ps.user_id,
                    ps.amount,
                    ledger_type,
                    ref_type="profit_share",
                    ref_id=ps.id,
                    remark=f"{ps.role_type.value}: order#{order_id}",
                )
            ps.status = ProfitStatus.SETTLED
            ps.settled_at = datetime.now(timezone.utc)
            settled_count += 1

        await db.commit()
        await _mark_idempotency_done(db, key)
    except Exception:
        raise

    return settled_count


async def request_withdrawal(
    db: AsyncSession, user_id: int, amount: float, remark: str | None = None
) -> Withdrawal:
    safety.guard_positive(amount, "withdrawal amount")
    if amount <= 0:
        raise safety.SafetyError("withdrawal amount must be greater than 0")

    wallet = await get_wallet(db, user_id)
    if not wallet:
        raise safety.SafetyError("wallet does not exist")
    if wallet.available_balance < amount:
        raise safety.SafetyError("insufficient wallet balance")

    withdrawal = Withdrawal(
        user_id=user_id,
        wallet_id=wallet.id,
        amount=amount,
        status=WithdrawalStatus.PENDING,
        remark=remark,
    )
    db.add(withdrawal)
    await db.commit()
    await db.refresh(withdrawal)

    key = make_key(KEY_WITHDRAW, withdrawal.id)
    ok, existing = await safety.acquire_idempotency_key(db, key)
    if not ok:
        await db.refresh(withdrawal)
        return withdrawal

    await safety.safe_freeze(
        db,
        user_id,
        amount,
        ref_type="withdrawal",
        ref_id=withdrawal.id,
        remark=f"withdrawal request: {remark or ''}",
    )
    await _mark_idempotency_done(db, key)
    await db.refresh(withdrawal)
    return withdrawal


async def _mark_idempotency_done(db: AsyncSession, key: str) -> None:
    from ..models.idempotency import IdempotencyKey

    result = await db.execute(select(IdempotencyKey).where(IdempotencyKey.key == key))
    ikey = result.scalar_one_or_none()
    if ikey:
        await safety.mark_idempotency_done(db, ikey)


def _withdraw_out_bill_no(withdrawal: Withdrawal) -> str:
    return withdrawal.transfer_out_bill_no or f"XJTX{withdrawal.id:010d}"


async def _complete_withdrawal(
    db: AsyncSession,
    withdrawal: Withdrawal,
    remark: str | None,
) -> Withdrawal:
    await safety.safe_unfreeze(
        db,
        withdrawal.user_id,
        withdrawal.amount,
        LedgerType.WITHDRAWAL_COMPLETE,
        ref_type="withdrawal",
        ref_id=withdrawal.id,
        remark=f"withdrawal completed: {remark or ''}",
    )
    withdrawal.status = WithdrawalStatus.APPROVED
    withdrawal.payout_status = "success"
    withdrawal.payout_at = datetime.now(timezone.utc)
    withdrawal.reviewed_at = withdrawal.reviewed_at or datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(withdrawal)
    return withdrawal


async def _reject_withdrawal(
    db: AsyncSession,
    withdrawal: Withdrawal,
    remark: str | None,
) -> Withdrawal:
    await safety.safe_unfreeze(
        db,
        withdrawal.user_id,
        withdrawal.amount,
        LedgerType.WITHDRAWAL_REJECT,
        ref_type="withdrawal",
        ref_id=withdrawal.id,
        remark=f"withdrawal rejected: {remark or ''}",
    )
    withdrawal.status = WithdrawalStatus.REJECTED
    withdrawal.payout_status = "rejected"
    withdrawal.reviewed_at = datetime.now(timezone.utc)
    withdrawal.remark = (withdrawal.remark or "") + f" | review: {remark or 'reject'}"
    await db.commit()
    await db.refresh(withdrawal)
    return withdrawal


async def _start_wechat_transfer(
    db: AsyncSession,
    withdrawal: Withdrawal,
    remark: str | None,
) -> Withdrawal:
    user = await db.get(User, withdrawal.user_id)
    if not user or not user.wechat_openid:
        raise ValueError("withdrawal user has no WeChat openid; ask the user to log in again")
    out_bill_no = _withdraw_out_bill_no(withdrawal)
    result = wechat_pay.create_transfer_bill(
        out_bill_no=out_bill_no,
        openid=user.wechat_openid,
        amount=withdrawal.amount,
        remark=remark or settings.WECHAT_TRANSFER_REMARK,
    )
    withdrawal.payout_provider = "wechat"
    withdrawal.payout_status = result.state
    withdrawal.transfer_out_bill_no = result.out_bill_no
    withdrawal.transfer_bill_no = result.transfer_bill_no
    withdrawal.transfer_payload = json.dumps(result.payload, ensure_ascii=False)
    withdrawal.reviewed_at = datetime.now(timezone.utc)
    withdrawal.remark = (withdrawal.remark or "") + f" | review: {remark or 'wechat transfer'}"

    if result.state in TRANSFER_SUCCESS_STATES:
        await db.commit()
        await db.refresh(withdrawal)
        return await _complete_withdrawal(db, withdrawal, remark)

    withdrawal.status = WithdrawalStatus.APPROVED
    await db.commit()
    await db.refresh(withdrawal)
    return withdrawal


async def review_withdrawal(
    db: AsyncSession,
    withdrawal_id: int,
    action: str,
    remark: str | None = None,
    payout_method: str = "manual",
) -> Withdrawal:
    withdrawal = await db.get(Withdrawal, withdrawal_id)
    if not withdrawal:
        raise ValueError("withdrawal not found")
    if withdrawal.status != WithdrawalStatus.PENDING:
        raise ValueError("withdrawal is not pending")

    if action == "reject":
        key = make_key(KEY_WITHDRAW_REVIEW, withdrawal_id)
        ok, existing = await safety.acquire_idempotency_key(db, key)
        if not ok:
            await db.refresh(withdrawal)
            return withdrawal
        result = await _reject_withdrawal(db, withdrawal, remark)
        await _mark_idempotency_done(db, key)
        return result

    if action != "approve":
        raise ValueError("invalid review action")

    use_wechat = payout_method == "wechat" or bool(settings.WECHAT_WITHDRAW_AUTO_TRANSFER)
    if use_wechat:
        return await _start_wechat_transfer(db, withdrawal, remark)

    key = make_key(KEY_WITHDRAW_REVIEW, withdrawal_id)
    ok, existing = await safety.acquire_idempotency_key(db, key)
    if not ok:
        await db.refresh(withdrawal)
        return withdrawal

    withdrawal.payout_provider = "manual"
    withdrawal.reviewed_at = datetime.now(timezone.utc)
    withdrawal.remark = (withdrawal.remark or "") + f" | review: {remark or 'manual approve'}"
    await db.commit()
    result = await _complete_withdrawal(db, withdrawal, remark)
    await _mark_idempotency_done(db, key)
    return result


def _transfer_state(payload: dict) -> str:
    return str(payload.get("state") or payload.get("status") or "processing").lower()


async def sync_wechat_withdrawal(db: AsyncSession, withdrawal_id: int) -> Withdrawal:
    withdrawal = await db.get(Withdrawal, withdrawal_id)
    if not withdrawal:
        raise ValueError("withdrawal not found")
    if withdrawal.payout_provider != "wechat":
        raise ValueError("withdrawal is not a WeChat transfer")
    out_bill_no = withdrawal.transfer_out_bill_no
    if not out_bill_no:
        raise ValueError("withdrawal missing transfer_out_bill_no")

    payload = wechat_pay.query_transfer_bill(out_bill_no)
    state = _transfer_state(payload)
    withdrawal.payout_status = state
    withdrawal.transfer_bill_no = payload.get("transfer_bill_no") or withdrawal.transfer_bill_no
    withdrawal.transfer_payload = json.dumps(payload, ensure_ascii=False)
    await db.commit()
    await db.refresh(withdrawal)

    if state in TRANSFER_SUCCESS_STATES and not withdrawal.payout_at:
        return await _complete_withdrawal(db, withdrawal, "wechat transfer synced")
    if state in TRANSFER_FAIL_STATES and withdrawal.status != WithdrawalStatus.REJECTED:
        return await _reject_withdrawal(db, withdrawal, "wechat transfer failed")
    return withdrawal


async def handle_wechat_transfer_notification(
    db: AsyncSession,
    headers: dict[str, str],
    body: str,
) -> Withdrawal:
    payload = wechat_pay.parse_notification(headers, body)
    out_bill_no = payload.get("out_bill_no")
    if not out_bill_no:
        raise ValueError("WeChat transfer notify missing out_bill_no")
    result = await db.execute(
        select(Withdrawal).where(Withdrawal.transfer_out_bill_no == out_bill_no)
    )
    withdrawal = result.scalar_one_or_none()
    if not withdrawal:
        raise ValueError(f"withdrawal not found by out_bill_no: {out_bill_no}")

    state = _transfer_state(payload)
    withdrawal.payout_status = state
    withdrawal.transfer_bill_no = payload.get("transfer_bill_no") or withdrawal.transfer_bill_no
    withdrawal.transfer_payload = json.dumps(payload, ensure_ascii=False)
    await db.commit()
    await db.refresh(withdrawal)

    if state in TRANSFER_SUCCESS_STATES and not withdrawal.payout_at:
        return await _complete_withdrawal(db, withdrawal, "wechat transfer notify")
    if state in TRANSFER_FAIL_STATES and withdrawal.status != WithdrawalStatus.REJECTED:
        return await _reject_withdrawal(db, withdrawal, "wechat transfer notify failed")
    return withdrawal


async def get_ledger(
    db: AsyncSession,
    user_id: int,
    skip: int = 0,
    limit: int = 50,
    ledger_type: str | None = None,
) -> list[Ledger]:
    stmt = select(Ledger).where(Ledger.user_id == user_id)
    if ledger_type:
        stmt = stmt.where(Ledger.type == ledger_type)
    stmt = stmt.order_by(Ledger.id.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    from ..models.order import Order
    from ..models.profit_share import ProfitShare
    share_ids = {r.reference_id for r in rows if r.reference_type == "profit_share" and r.reference_id}
    shares = {}
    if share_ids:
        shares = {p.id: p for p in (await db.execute(select(ProfitShare).where(ProfitShare.id.in_(share_ids)))).scalars()}
    order_ids = {p.order_id for p in shares.values()}
    order_ids.update(r.reference_id for r in rows if r.reference_type == "order" and r.reference_id)
    orders = {}
    if order_ids:
        orders = {o.id: o for o in (await db.execute(select(Order).where(Order.id.in_(order_ids)))).scalars()}
    labels = {
        "order_income": "订单收入", "profit_settlement": "收益结算",
        "technician_wage": "师傅工资", "monthly_wage_payment": "月薪发放",
        "refund_clawback": "退款扣回", "manual_adjust": "人工调整",
        "withdrawal": "提现支出", "withdrawal_complete": "提现完成",
        "withdrawal_reject": "提现退回", "ledger_freeze": "资金冻结",
        "ledger_unfreeze": "资金解冻",
    }
    profit_labels = {
        "store_revenue": "门店收入", "store_manager_commission": "店长佣金",
        "city_manager_commission": "城市经理佣金", "channel_manager_commission": "推广经理佣金",
        "tech_support": "技术服务收益", "referral_reward": "推荐奖励",
        "proxy_assist_reward": "代客下单奖励", "technician_wage": "师傅工资",
        "pass_through": "代收款", "platform_retained": "平台收益",
    }
    output = []
    for row in rows:
        share = shares.get(row.reference_id) if row.reference_type == "profit_share" else None
        order_id = share.order_id if share else (row.reference_id if row.reference_type == "order" else None)
        order = orders.get(order_id)
        label = profit_labels.get(share.role_type.value, "收益结算") if share else labels.get(row.type.value, "资金流水")
        if row.reference_type == "withdrawal" and row.type == LedgerType.LEDGER_FREEZE:
            label = "提现申请（资金冻结）"
        output.append({
            **{column.name: getattr(row, column.name) for column in Ledger.__table__.columns},
            "display_label": label,
            "service_address": (order.address or order.customer_address_snapshot) if order else None,
            "order_id": order_id,
        })
    return output


async def list_withdrawals(
    db: AsyncSession,
    user_id: int | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> list[Withdrawal]:
    stmt = select(Withdrawal)
    if user_id:
        stmt = stmt.where(Withdrawal.user_id == user_id)
    if status:
        stmt = stmt.where(Withdrawal.status == _coerce_withdrawal_status(status))
    stmt = stmt.order_by(Withdrawal.id.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())
