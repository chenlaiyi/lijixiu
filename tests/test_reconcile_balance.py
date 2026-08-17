"""对账回归测试:验证 ledger.amount 语义与 wallet.total 一致。

修复前 bug:
- safe_freeze: 写 -amount(应写 0,total 不变)
- safe_unfreeze(COMPLETE): 写 0(应写 -amount,total -amount)

修复后(2026-08-09):
- safe_deposit: amount=+amount, total +amount
- safe_withdraw: amount=-amount, total -amount
- safe_freeze: amount=0, total 0
- safe_unfreeze(COMPLETE): amount=-amount, total -amount
- safe_unfreeze(REJECT): amount=0, total 0
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

TEMP_DIR = tempfile.TemporaryDirectory(prefix="xiulijiu-recon-")
DB_PATH = Path(TEMP_DIR.name) / "recon.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"
os.environ["SMS_PROVIDER"] = "debug"
os.environ["SMS_DEBUG_CODE"] = "246810"
os.environ["PAYMENT_ALLOW_MOCK"] = "true"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.core.database import async_session, init_db  # noqa: E402
from app.models.ledger import LedgerType  # noqa: E402
from app.services import safety  # noqa: E402


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


async def _ledger_sum(db, user_id: int) -> float:
    r = await db.execute(
        select(func.coalesce(func.sum(Ledger.__table__.c.amount), 0.0)).where(
            Ledger.__table__.c.user_id == user_id
        )
    )
    return float(r.scalar() or 0.0)


def _total(wallet) -> float:
    return float(wallet.available_balance + wallet.frozen_balance)


def _diff(ledger_sum: float, total: float) -> float:
    return round(ledger_sum - total, 2)


async def _case_deposit():
    async with async_session() as db:
        w = await safety.safe_deposit(db, user_id=9001, amount=100, ledger_type=LedgerType.ORDER_INCOME)
        s = await _ledger_sum(db, 9001)
        t = _total(w)
        return _diff(s, t), s, t


async def _case_withdraw():
    async with async_session() as db:
        await safety.safe_deposit(db, user_id=9002, amount=200, ledger_type=LedgerType.ORDER_INCOME)
        w = await safety.safe_debit(db, user_id=9002, amount=50, ledger_type=LedgerType.MANUAL_ADJUST)
        s = await _ledger_sum(db, 9002)
        t = _total(w)
        return _diff(s, t), s, t


async def _case_freeze():
    async with async_session() as db:
        await safety.safe_deposit(db, user_id=9003, amount=300, ledger_type=LedgerType.ORDER_INCOME)
        w = await safety.safe_freeze(db, user_id=9003, amount=120)
        s = await _ledger_sum(db, 9003)
        t = _total(w)
        return _diff(s, t), s, t


async def _case_complete():
    async with async_session() as db:
        await safety.safe_deposit(db, user_id=9004, amount=300, ledger_type=LedgerType.ORDER_INCOME)
        await safety.safe_freeze(db, user_id=9004, amount=120)
        w = await safety.safe_unfreeze(
            db, user_id=9004, amount=120, ledger_type=LedgerType.WITHDRAWAL_COMPLETE
        )
        s = await _ledger_sum(db, 9004)
        t = _total(w)
        return _diff(s, t), s, t


async def _case_reject():
    async with async_session() as db:
        await safety.safe_deposit(db, user_id=9005, amount=300, ledger_type=LedgerType.ORDER_INCOME)
        await safety.safe_freeze(db, user_id=9005, amount=120)
        w = await safety.safe_unfreeze(
            db, user_id=9005, amount=120, ledger_type=LedgerType.WITHDRAWAL_REJECT
        )
        s = await _ledger_sum(db, 9005)
        t = _total(w)
        return _diff(s, t), s, t


async def _case_full_flow():
    async with async_session() as db:
        await safety.safe_deposit(db, user_id=9006, amount=1000, ledger_type=LedgerType.ORDER_INCOME)
        await safety.safe_freeze(db, user_id=9006, amount=300)
        w = await safety.safe_unfreeze(
            db, user_id=9006, amount=300, ledger_type=LedgerType.WITHDRAWAL_COMPLETE
        )
        s = await _ledger_sum(db, 9006)
        t = _total(w)
        return _diff(s, t), s, t, t


# 用延迟 import 避免在 init_db 之前导入
from app.models.ledger import Ledger  # noqa: E402


async def _main():
    await init_db()
    cases = [
        ('deposit',         await _case_deposit()),
        ('withdraw',        await _case_withdraw()),
        ('freeze',          await _case_freeze()),
        ('complete',        await _case_complete()),
        ('reject',          await _case_reject()),
        ('full_flow',       await _case_full_flow()),
    ]
    failed = 0
    for name, result in cases:
        diff = result[0]
        ok = diff == 0
        print(('OK  ' if ok else 'FAIL') + f' {name:12s} diff={diff} ' + ' '.join(str(x) for x in result[1:]))
        if not ok:
            failed += 1
    print('---')
    print(f'{len(cases) - failed}/{len(cases)} passed')
    return failed


if __name__ == '__main__':
    failed = asyncio.run(_main())
    sys.exit(0 if failed == 0 else 1)
