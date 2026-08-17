"""协议版本管理 + 数据访问请求单元测试(2026-08-09)。

覆盖《个保法》合规要求:
  - /me 返 agreements_current + agreements_need_renewal
  - POST /me/agreements 记录用户同意版本
  - POST /me/export-data 导出个人数据(数据可携权)
  - POST /me/delete 申请删除(15 日宽限期)
  - POST /me/cancel-deletion 撤回
"""
import os
import sys
import tempfile
from pathlib import Path

TEMP_DIR = tempfile.TemporaryDirectory(prefix="xiulijiu-agree-")
DB_PATH = Path(TEMP_DIR.name) / "agree.db"
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
from app.models.user import BusinessRole, User, UserRole  # noqa: E402
from app.routers.auth import CURRENT_TERMS_VERSION, CURRENT_PRIVACY_VERSION  # noqa: E402
from app.schemas.user import AgreementRequest  # noqa: E402


async def _setup():
    """创建测试用户。"""
    from app.core.database import async_session
    from sqlalchemy import select

    await init_db()
    async with async_session() as db:
        for uid, br, role in [
            (8001, BusinessRole.CUSTOMER, UserRole.CUSTOMER),
            (8002, BusinessRole.PLATFORM_ADMIN, UserRole.ADMIN),
        ]:
            existing = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
            if not existing:
                db.add(User(
                    id=uid,
                    phone=f"139{uid:08d}",
                    name=f"user{uid}",
                    role=role,
                    business_role=br.value,
                ))
        await db.commit()


def main_sync():
    asyncio.run(_setup())

    customer_token = make_token(8001, "customer")
    admin_token = make_token(8002, "admin")
    customer_auth = {"Authorization": f"Bearer {customer_token}"}

    client = TestClient(app)
    results = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))
        print(("OK  " if ok else "FAIL") + f" {name:48s} {detail}")

    # === 1. /me 返 agreements_current + agreements_need_renewal ===
    r = client.get("/api/v1/auth/me", headers=customer_auth)
    check("me-status-200", r.status_code == 200, f"status={r.status_code}")
    body = r.json()
    check("me-has-agreements-current", "agreements_current" in body)
    check("me-agreements-current-terms", body.get("agreements_current", {}).get("terms") == CURRENT_TERMS_VERSION)
    check("me-agreements-current-privacy", body.get("agreements_current", {}).get("privacy") == CURRENT_PRIVACY_VERSION)
    check("me-need-renewal-initially", body.get("agreements_need_renewal") is True, f"need_renewal={body.get('agreements_need_renewal')}")

    # === 2. 无 token 401 ===
    r = client.get("/api/v1/auth/me")
    check("me-no-auth-401", r.status_code == 401, f"status={r.status_code}")

    # === 3. POST /me/agreements 记录同意 ===
    r = client.post(
        "/api/v1/auth/me/agreements",
        json={"terms_version": CURRENT_TERMS_VERSION, "privacy_version": CURRENT_PRIVACY_VERSION},
        headers=customer_auth,
    )
    check("agreements-record-200", r.status_code == 200, f"status={r.status_code} body={r.text[:150]}")
    body = r.json()
    check("agreements-record-no-need-renewal", body.get("need_renewal") is False)

    # === 4. /me 现在不再需要 renewal ===
    r = client.get("/api/v1/auth/me", headers=customer_auth)
    body = r.json()
    check("me-after-agreed-no-renewal", body.get("agreements_need_renewal") is False)
    check("me-after-agreed-terms-version", body.get("agreed_terms_version") == CURRENT_TERMS_VERSION)
    check("me-after-agreed-privacy-version", body.get("agreed_privacy_version") == CURRENT_PRIVACY_VERSION)
    check("me-after-agreed-has-timestamp", body.get("agreed_at") is not None)

    # === 5. 旧版本号被拒(需要 renewal) ===
    r = client.get("/api/v1/auth/me", headers=customer_auth)
    body = r.json()
    # 模拟版本升级:用旧版本号写入,检查 need_renewal 重新为 True
    from app.core.database import async_session
    from app.models.user import User
    from sqlalchemy import update

    async def bump_version():
        async with async_session() as db:
            await db.execute(
                update(User).where(User.id == 8001).values(
                    agreed_terms_version="v0.9",  # 旧版本
                    agreed_privacy_version="v0.9",
                )
            )
            await db.commit()
    asyncio.run(bump_version())

    r = client.get("/api/v1/auth/me", headers=customer_auth)
    body = r.json()
    check("me-need-renewal-on-version-mismatch", body.get("agreements_need_renewal") is True, f"need_renewal={body.get('agreements_need_renewal')}")

    # === 6. POST /me/export-data 导出个人数据 ===
    r = client.post("/api/v1/auth/me/export-data", headers=customer_auth)
    check("export-status-200", r.status_code == 200, f"status={r.status_code}")
    body = r.json()
    check("export-has-user", isinstance(body.get("user"), dict))
    check("export-has-agreements", isinstance(body.get("agreements"), dict))
    check("export-has-orders", isinstance(body.get("orders"), list))
    check("export-has-wallet", "wallet" in body)
    check("export-has-ledger-count", "ledger_count" in body)
    check("export-has-support-tickets", isinstance(body.get("support_tickets"), list))
    check("export-has-addresses", isinstance(body.get("addresses"), list))
    check("export-has-note", "个保法" in body.get("note", ""))
    check("export-has-timestamp", "exported_at" in body)
    # user 不能包含其他用户的敏感信息
    check("export-user-only-self", body.get("user", {}).get("id") == 8001)

    # === 7. POST /me/delete 申请删除 ===
    r = client.post("/api/v1/auth/me/delete", headers=customer_auth)
    check("delete-status-200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    body = r.json()
    check("delete-has-scheduled-at", "deletion_scheduled_at" in body)
    check("delete-grace-period-15", body.get("grace_period_days") == 15)

    # === 8. 重复申请 ===
    r = client.post("/api/v1/auth/me/delete", headers=customer_auth)
    check("delete-already-200", r.status_code == 200)
    body = r.json()
    check("delete-already-flag", body.get("already_scheduled") is True)

    # === 9. /me 显示 deletion_scheduled_at ===
    r = client.get("/api/v1/auth/me", headers=customer_auth)
    body = r.json()
    check("me-shows-deletion-scheduled", body.get("deletion_scheduled_at") is not None)

    # === 10. POST /me/cancel-deletion 撤回 ===
    r = client.post("/api/v1/auth/me/cancel-deletion", headers=customer_auth)
    check("cancel-status-200", r.status_code == 200)
    check("cancel-message", "撤回" in r.json().get("message", ""))

    # === 11. /me 不再显示 deletion_scheduled_at ===
    r = client.get("/api/v1/auth/me", headers=customer_auth)
    body = r.json()
    check("me-no-deletion-after-cancel", body.get("deletion_scheduled_at") is None)

    # === 12. 跨用户隔离(用户 8001 不能操作 8002 的数据)===
    # 我们的 export-data 通过 token 拿 user,自动隔离,这里只验证 admin 不能直接拿 customer 数据
    # admin 自己的 /me 应该正常
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    check("admin-me-200", r.status_code == 200)
    body = r.json()
    check("admin-me-self-id", body.get("id") == 8002, f"id={body.get('id')}")

    # === 13. 协议 schema 校验 ===
    # 缺字段应该 422
    r = client.post("/api/v1/auth/me/agreements", json={"terms_version": "v1.0"}, headers=customer_auth)
    check("agreements-422-on-missing", r.status_code == 422)
    # 短字符串(< 1) 拒绝
    r = client.post("/api/v1/auth/me/agreements", json={"terms_version": "", "privacy_version": "v1.0"}, headers=customer_auth)
    check("agreements-422-on-empty", r.status_code == 422)

    # === summary ===
    print("---")
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main_sync())
