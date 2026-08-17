"""资金安全层 — 幂等 + 事务锁 + 对账 + 守卫

所有资金操作必须通过本模块，禁止直接修改 Wallet/Ledger。
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.idempotency import IdempotencyKey, IdempotencyStatus, make_key
from ..models.ledger import Ledger, LedgerType
from ..models.reconciliation import ReconciliationLog, ReconcileStatus
from ..models.wallet import Wallet


# ═══════════════════════════════════════════════════════════════════
# 幂等层
# ═══════════════════════════════════════════════════════════════════

async def acquire_idempotency_key(
    db: AsyncSession, key: str
) -> tuple[bool, IdempotencyKey | None]:
    """尝试获取幂等键。返回 (成功?, 现有记录或None)。

    - 如果 key 不存在 → 创建(processing) → 返回 True
    - 如果 key status=done → 返回 False + 已有记录
    - 如果 key status=processing → 返回 False + 已有记录（并发冲突）
    """
    result = await db.execute(
        select(IdempotencyKey).where(IdempotencyKey.key == key)
    )
    existing = result.scalar_one_or_none()

    if existing:
        return False, existing

    ikey = IdempotencyKey(key=key, status=IdempotencyStatus.PROCESSING)
    db.add(ikey)
    await db.commit()
    return True, ikey


async def mark_idempotency_done(
    db: AsyncSession, ikey: IdempotencyKey, result_json: str | None = None
):
    """标记幂等键为 done"""
    ikey.status = IdempotencyStatus.DONE
    ikey.result = result_json
    await db.commit()


# ═══════════════════════════════════════════════════════════════════
# 钱包安全锁
# ═══════════════════════════════════════════════════════════════════

async def lock_wallet(db: AsyncSession, user_id: int) -> Wallet | None:
    """SELECT ... FOR UPDATE 锁定钱包，防止并发"""
    result = await db.execute(
        select(Wallet)
        .where(Wallet.user_id == user_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def get_or_create_wallet_locked(db: AsyncSession, user_id: int) -> Wallet:
    """获取或创建钱包（带锁）"""
    wallet = await lock_wallet(db, user_id)
    if wallet:
        return wallet

    wallet = Wallet(user_id=user_id)
    db.add(wallet)
    await db.commit()

    # 重新获取带锁
    return await lock_wallet(db, user_id)


# ═══════════════════════════════════════════════════════════════════
# 安全守卫
# ═══════════════════════════════════════════════════════════════════

class SafetyError(ValueError):
    """资金安全违规"""
    pass


def guard_positive(amount: float, label: str = "amount"):
    """金额必须 >= 0"""
    if amount < 0:
        raise SafetyError(f"{label} 不能为负数: {amount}")


def guard_sufficient(wallet: Wallet, amount: float):
    """余额充足检查"""
    if wallet.available_balance < amount:
        raise SafetyError(
            f"余额不足: 可用{wallet.available_balance}, 需要{amount}"
        )


def guard_frozen_consistency(wallet: Wallet):
    """冻结余额不能为负"""
    if wallet.frozen_balance < 0:
        raise SafetyError(
            f"冻结余额异常(负): {wallet.frozen_balance}"
        )


def guard_available_consistency(wallet: Wallet):
    """可用余额不能为负"""
    if wallet.available_balance < 0:
        raise SafetyError(
            f"可用余额异常(负): {wallet.available_balance}"
        )


# ═══════════════════════════════════════════════════════════════════
# 安全资金操作（带锁 + 守卫）
# ═══════════════════════════════════════════════════════════════════

async def safe_deposit(
    db: AsyncSession,
    user_id: int,
    amount: float,
    ledger_type: LedgerType,
    ref_type: str | None = None,
    ref_id: int | None = None,
    remark: str | None = None,
) -> Wallet:
    """安全入账：加锁 → 守卫 → 更新 → 流水"""
    guard_positive(amount, "入账金额")

    wallet = await get_or_create_wallet_locked(db, user_id)

    wallet.available_balance += amount
    wallet.total_income += amount

    guard_available_consistency(wallet)

    # 流水（只追加，不可修改）
    ledger = Ledger(
        wallet_id=wallet.id,
        user_id=user_id,
        type=ledger_type,
        amount=amount,
        balance_after=wallet.available_balance,
        reference_type=ref_type,
        reference_id=ref_id,
        remark=remark,
    )
    db.add(ledger)

    await db.commit()
    return wallet


async def safe_transfer(
    db: AsyncSession,
    from_user_id: int,
    to_user_id: int,
    amount: float,
    debit_type: LedgerType,
    credit_type: LedgerType,
    ref_type: str | None = None,
    ref_id: int | None = None,
    remark: str | None = None,
) -> tuple[Wallet, Wallet]:
    """Move money between two platform wallets with append-only ledgers."""
    guard_positive(amount, "转账金额")
    if amount <= 0:
        raise SafetyError("转账金额必须大于0")
    source = await lock_wallet(db, from_user_id)
    if not source:
        raise SafetyError(f"付款钱包不存在: user#{from_user_id}")
    target = await get_or_create_wallet_locked(db, to_user_id)
    guard_sufficient(source, amount)
    source.available_balance -= amount
    target.available_balance += amount
    target.total_income += amount
    db.add(Ledger(
        wallet_id=source.id,
        user_id=from_user_id,
        type=debit_type,
        amount=-amount,
        balance_after=source.available_balance,
        reference_type=ref_type,
        reference_id=ref_id,
        remark=remark,
    ))
    db.add(Ledger(
        wallet_id=target.id,
        user_id=to_user_id,
        type=credit_type,
        amount=amount,
        balance_after=target.available_balance,
        reference_type=ref_type,
        reference_id=ref_id,
        remark=remark,
    ))
    await db.commit()
    return source, target


async def safe_debit(
    db: AsyncSession,
    user_id: int,
    amount: float,
    ledger_type: LedgerType,
    ref_type: str | None = None,
    ref_id: int | None = None,
    remark: str | None = None,
) -> Wallet:
    guard_positive(amount, "扣款金额")
    wallet = await lock_wallet(db, user_id)
    if not wallet:
        raise SafetyError(f"钱包不存在: user#{user_id}")
    guard_sufficient(wallet, amount)
    wallet.available_balance -= amount
    db.add(Ledger(
        wallet_id=wallet.id,
        user_id=user_id,
        type=ledger_type,
        amount=-amount,
        balance_after=wallet.available_balance,
        reference_type=ref_type,
        reference_id=ref_id,
        remark=remark,
    ))
    await db.commit()
    return wallet


async def safe_freeze(
    db: AsyncSession,
    user_id: int,
    amount: float,
    ref_type: str | None = None,
    ref_id: int | None = None,
    remark: str | None = None,
) -> Wallet:
    """安全冻结：加锁 → 守卫 → 扣可用 → 加冻结 → 流水"""
    guard_positive(amount, "冻结金额")

    wallet = await lock_wallet(db, user_id)
    if not wallet:
        raise SafetyError(f"钱包不存在: user#{user_id}")

    guard_sufficient(wallet, amount)

    wallet.available_balance -= amount
    wallet.frozen_balance += amount

    guard_available_consistency(wallet)
    guard_frozen_consistency(wallet)

    # NOTE: 冻结是钱包内"可用→冻结"转移,wallet total (available+frozen) 不变,
    # 所以 ledger amount 写 0,只用 type=LEDGER_FREEZE 标记事件(2026-08-09 修复)。
    ledger = Ledger(
        wallet_id=wallet.id,
        user_id=user_id,
        type=LedgerType.LEDGER_FREEZE,
        amount=0,
        balance_after=wallet.available_balance,
        reference_type=ref_type,
        reference_id=ref_id,
        remark=remark or "freeze: move available to frozen",
    )
    db.add(ledger)

    await db.commit()
    return wallet


async def safe_unfreeze(
    db: AsyncSession,
    user_id: int,
    amount: float,
    ledger_type: LedgerType,
    ref_type: str | None = None,
    ref_id: int | None = None,
    remark: str | None = None,
) -> Wallet:
    """安全解冻/扣款：加锁 → 守卫 → 扣冻结 → 流水"""
    guard_positive(amount, "解冻金额")

    wallet = await lock_wallet(db, user_id)
    if not wallet:
        raise SafetyError(f"钱包不存在: user#{user_id}")

    if wallet.frozen_balance < amount:
        raise SafetyError(
            f"冻结余额不足: 冻结{wallet.frozen_balance}, 需要{amount}"
        )

    wallet.frozen_balance -= amount

    # 如果是拒绝返还，加回可用余额(总账视角 +amount,因为钱从 frozen 回到了 available)
    if ledger_type == LedgerType.WITHDRAWAL_REJECT:
        wallet.available_balance += amount

    guard_available_consistency(wallet)
    guard_frozen_consistency(wallet)

    # NOTE: 解冻/扣款的 ledger 语义
    # - WITHDRAWAL_REJECT:钱从 frozen 回到 available,total 不变,ledger 写 0(标记事件)
    # - WITHDRAWAL_COMPLETE / WITHDRAWAL_TRANSFER:钱从 frozen 真正出账,total -amount,ledger 写 -amount
    # 修复前 ledger amount 写 amount if REJECT else 0(总是错的)(2026-08-09)
    if ledger_type == LedgerType.WITHDRAWAL_REJECT:
        ledger_amount = 0
    else:
        ledger_amount = -amount

    ledger = Ledger(
        wallet_id=wallet.id,
        user_id=user_id,
        type=ledger_type,
        amount=ledger_amount,
        balance_after=wallet.available_balance,
        reference_type=ref_type,
        reference_id=ref_id,
        remark=remark,
    )
    db.add(ledger)

    await db.commit()
    return wallet


# ═══════════════════════════════════════════════════════════════════
# 对账引擎
# ═══════════════════════════════════════════════════════════════════

async def run_reconciliation(db: AsyncSession) -> list[ReconciliationLog]:
    """全量对账：比较每个钱包的余额与账本汇总"""
    logs = []

    wallets = (await db.execute(select(Wallet))).scalars().all()

    for wallet in wallets:
        # 账本汇总 = 所有 ledger 的 amount 代数和
        result = await db.execute(
            select(func.coalesce(func.sum(Ledger.amount), 0.0))
            .where(Ledger.wallet_id == wallet.id)
        )
        ledger_sum = result.scalar() or 0.0

        actual = wallet.available_balance + wallet.frozen_balance
        difference = round(ledger_sum - actual, 2)

        status = ReconcileStatus.OK if abs(difference) < 0.01 else ReconcileStatus.MISMATCH

        log = ReconciliationLog(
            wallet_id=wallet.id,
            user_id=wallet.user_id,
            expected_balance=round(ledger_sum, 2),
            actual_balance=round(actual, 2),
            difference=difference,
            status=status,
            detail=(
                f"ledger_sum={ledger_sum:.2f} wallet_sum={actual:.2f} "
                f"(available={wallet.available_balance} frozen={wallet.frozen_balance})"
                if status == ReconcileStatus.MISMATCH else None
            ),
        )
        db.add(log)
        logs.append(log)

    await db.commit()
    return logs


async def safe_reconcile_adjust(
    db: AsyncSession,
    user_id: int,
    amount: float,
    remark: str | None = None,
    operator_user_id: int | None = None,
) -> tuple[Wallet, Ledger]:
    """对账修复:只写 ledger 不动 wallet(2026-08-09 P0 收尾)。

    用途:历史对账差异已知是非真实问题,补一条 MANUAL_ADJUST ledger 让 ledger_sum == wallet total。
    必须由 admin 触发(端点侧加 require_admin)。
    """
    wallet = await lock_wallet(db, user_id)
    if not wallet:
        raise SafetyError(f"钱包不存在: user#{user_id}")

    ledger = Ledger(
        wallet_id=wallet.id,
        user_id=user_id,
        type=LedgerType.MANUAL_ADJUST,
        amount=amount,
        balance_after=wallet.available_balance,
        reference_type="reconcile_adjust",
        reference_id=operator_user_id,
        remark=remark or "对账差异修复",
    )
    db.add(ledger)
    await db.commit()
    await db.refresh(wallet)
    await db.refresh(ledger)
    return wallet, ledger


async def get_last_reconciliation(
    db: AsyncSession, limit: int = 50
) -> list[ReconciliationLog]:
    result = await db.execute(
        select(ReconciliationLog)
        .order_by(ReconciliationLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
