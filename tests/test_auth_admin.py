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
from app.core.config import settings  # noqa: E402
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

    # === 2026-10-07:管理后台账号密码登录(替代手工粘贴 token)===
    # 未配置时必须是 503,不能默默放行
    r = client.post("/api/v1/auth/admin-login", json={"account": "ops", "password": "x"})
    check("admin_login_unconfigured_503", r.status_code == 503, f"status={r.status_code}")

    # 配置后:正确凭据 200 且角色为 platform_admin;错误凭据 401
    os.environ["ADMIN_WEB_ACCOUNT"] = "ops"
    os.environ["ADMIN_WEB_PASSWORD"] = "OpsPass123!@#"
    os.environ["ADMIN_WEB_PHONE"] = "18800000000"
    settings.ADMIN_WEB_ACCOUNT = "ops"
    settings.ADMIN_WEB_PASSWORD = "OpsPass123!@#"
    settings.ADMIN_WEB_PHONE = "18800000000"

    r = client.post("/api/v1/auth/admin-login", json={"account": "ops", "password": "OpsPass123!@#"})
    check("admin_login_200", r.status_code == 200, f"status={r.status_code} body={r.text[:120]}")
    if r.status_code == 200:
        payload = r.json()
        check("admin_login_role_platform_admin",
              payload["user"]["business_role"] == "platform_admin",
              payload["user"]["business_role"])
        check("admin_login_returns_token", bool(payload.get("token")))
        # 拿到的 token 必须能过 admin 接口
        r2 = client.post("/api/v1/admin/reconcile/run",
                         headers={"Authorization": f"Bearer {payload['token']}"})
        check("admin_login_token_can_call_admin", r2.status_code == 200, f"status={r2.status_code}")

    r = client.post("/api/v1/auth/admin-login", json={"account": "ops", "password": "wrong"})
    check("admin_login_wrong_password_401", r.status_code == 401, f"status={r.status_code}")
    r = client.post("/api/v1/auth/admin-login", json={"account": "nobody", "password": "OpsPass123!@#"})
    check("admin_login_wrong_account_401", r.status_code == 401, f"status={r.status_code}")

    # === 2026-10-07:后台概览指标走 Bearer 端点,不再调 /metrics ===
    # 背景:后台原来 fetch("/metrics"),而该路径有 nginx basic auth
    # -> 浏览器登录后台后还会弹一个原生账号密码框。
    if admin_token:
        r = client.get("/api/v1/admin/metrics",
                       headers={"Authorization": f"Bearer {admin_token}"})
        check("admin_metrics_200", r.status_code == 200, f"status={r.status_code}")
        if r.status_code == 200:
            data = r.json()
            for key in ("orders_total", "orders_completed", "orders_pending",
                        "wallets_total", "total_balance", "alerts_active"):
                check(f"admin_metrics_has_{key}", key in data, str(list(data.keys()))[:80])
            # 与 /metrics 共用同一份口径:业务字段必须一致
            plain = client.get("/metrics").json()
            shared = {k: v for k, v in data.items() if k in plain}
            same = all(plain[k] == v for k, v in shared.items())
            check("admin_metrics_matches_metrics", same and bool(shared),
                  f"shared={shared}")

    r = client.get("/api/v1/admin/metrics")
    check("admin_metrics_no_token_401", r.status_code == 401, f"status={r.status_code}")

    r = client.get("/api/v1/admin/metrics", headers={"Authorization": f"Bearer {customer_token}"})
    check("admin_metrics_customer_403", r.status_code == 403, f"status={r.status_code}")

    # === Summary ===
    print("---")
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main_sync())
