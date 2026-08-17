"""鉴权 + admin adjust 回归测试(2026-08-09 P0 收尾)。

覆盖:
- 未带 Authorization 头 → 401
- 无效 token → 401
- 普通用户查别人钱包 → 403
- 普通用户查自己钱包 → 200
- 非 admin 调 /admin/* → 403
- admin 调 /admin/reconcile/run → 200
- admin 调 /admin/wallet/adjust → 200 + 写 ledger
- 调完 adjust 后 ledger_sum 变化(用于消化对账差异)
"""
import os
import sys
import tempfile
from pathlib import Path

TEMP_DIR = tempfile.TemporaryDirectory(prefix="xiulijiu-auth-")
DB_PATH = Path(TEMP_DIR.name) / "auth.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"
os.environ["SMS_PROVIDER"] = "debug"
os.environ["SMS_DEBUG_CODE"] = "246810"
os.environ["PAYMENT_ALLOW_MOCK"] = "true"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.core.auth import make_token  # noqa: E402
from app.core.database import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.ledger import LedgerType  # noqa: E402
from app.services import safety  # noqa: E402


async def _setup_users():
    """创建测试用户:admin + customer + repairer。"""
    from app.core.database import async_session
    from app.models.user import BusinessRole, User, UserRole
    from sqlalchemy import select

    await init_db()
    async with async_session() as db:
        for uid, br, role in [
            (9001, BusinessRole.CUSTOMER, UserRole.CUSTOMER),
            (9002, BusinessRole.PLATFORM_ADMIN, UserRole.ADMIN),
            (9003, BusinessRole.REPAIRER, UserRole.REPAIRER),
        ]:
            existing = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
            if not existing:
                db.add(User(id=uid, phone=f"139{uid:08d}", name=f"user{uid}", role=role, business_role=br.value))
        await db.commit()


def main_sync():
    asyncio.run(_setup_users())

    customer_token = make_token(9001, "customer")
    admin_token = make_token(9002, "admin")
    repairer_token = make_token(9003, "repairer")

    client = TestClient(app)
    results = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))
        print(("OK  " if ok else "FAIL") + f" {name:50s} {detail}")

    # === Auth basics ===
    r = client.get("/api/v1/wallet/balance/9001")
    check("no_token_wallet_401", r.status_code == 401, f"status={r.status_code}")

    r = client.get("/api/v1/wallet/balance/9001", headers={"Authorization": "Bearer invalid.token"})
    check("bad_token_wallet_401", r.status_code == 401, f"status={r.status_code}")

    r = client.get("/api/v1/wallet/balance/9001", headers={"Authorization": f"Bearer {customer_token}"})
    check("self_balance_200", r.status_code == 200, f"status={r.status_code}")

    r = client.get("/api/v1/wallet/balance/9003", headers={"Authorization": f"Bearer {customer_token}"})
    check("other_balance_403", r.status_code == 403, f"status={r.status_code}")

    r = client.get("/api/v1/wallet/balance/9003", headers={"Authorization": f"Bearer {admin_token}"})
    check("admin_see_any_200", r.status_code == 200, f"status={r.status_code}")

    # === Admin endpoints ===
    r = client.post("/api/v1/admin/reconcile/run")
    check("reconcile_no_auth_401", r.status_code == 401, f"status={r.status_code}")

    r = client.post("/api/v1/admin/reconcile/run", headers={"Authorization": f"Bearer {customer_token}"})
    check("reconcile_customer_403", r.status_code == 403, f"status={r.status_code}")

    r = client.post("/api/v1/admin/reconcile/run", headers={"Authorization": f"Bearer {repairer_token}"})
    check("reconcile_repairer_403", r.status_code == 403, f"status={r.status_code}")

    r = client.post("/api/v1/admin/reconcile/run", headers={"Authorization": f"Bearer {admin_token}"})
    check("reconcile_admin_200", r.status_code == 200, f"status={r.status_code}")

    r = client.get("/api/v1/admin/alerts", headers={"Authorization": f"Bearer {admin_token}"})
    check("alerts_admin_200", r.status_code == 200, f"status={r.status_code}")

    r = client.get("/api/v1/admin/alerts", headers={"Authorization": f"Bearer {customer_token}"})
    check("alerts_customer_403", r.status_code == 403, f"status={r.status_code}")

    # === Adjust endpoint ===
    # 先构造一个对账差异(直接用 SQL 不通过 safety)
    from app.core.database import async_session
    from app.models.wallet import Wallet
    from sqlalchemy import update

    async def create_diff():
        async with async_session() as db:
            await db.execute(update(Wallet).where(Wallet.user_id == 9003).values(frozen_balance=200.0))
            await db.commit()

    asyncio.run(create_diff())

    # 调对账,确认有 mismatch
    r = client.post("/api/v1/admin/reconcile/run", headers={"Authorization": f"Bearer {admin_token}"})
    body = r.json()
    has_diff = any(d["user_id"] == 9003 for d in body.get("details", []))
    check("diff_detected_for_9003", has_diff, f"details={body.get('details', [])}")

    # 调 adjust
    r = client.post(
        "/api/v1/admin/wallet/adjust",
        json={"user_id": 9003, "amount": 200.0, "remark": "test fix"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    check("adjust_admin_200", r.status_code == 200, f"status={r.status_code} body={r.text[:120]}")

    # 非 admin 调 adjust
    r = client.post(
        "/api/v1/admin/wallet/adjust",
        json={"user_id": 9003, "amount": 200.0},
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    check("adjust_customer_403", r.status_code == 403, f"status={r.status_code}")

    # 调对账,确认 9003 的差异消了
    r = client.post("/api/v1/admin/reconcile/run", headers={"Authorization": f"Bearer {admin_token}"})
    body = r.json()
    has_diff = any(d["user_id"] == 9003 for d in body.get("details", []))
    check("diff_resolved_for_9003", not has_diff, f"details={body.get('details', [])}")

    # === Summary ===
    print("---")
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main_sync())
