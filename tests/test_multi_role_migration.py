"""多角色:迁移兼容 + 越权边界回归(2026-10-07)。

本文件做两件事:

1. **存量库迁移**:在临时库里建一张「老结构」users 表(只有 business_role,
   没有 business_roles / active_business_role),跑 init_db,断言
   - 新列被补上
   - 老用户的 business_roles 被回填成 [business_role]
   - active_business_role 指向原角色(不会掉回客户)
   - init_db 重复执行安全(幂等)

2. **越权边界**:多角色不能变成提权通道
   - 客户 PATCH 自己加角色 → 403
   - 非管理员 PATCH 别人角色 → 403
   - 用户切换到自己没有的角色 → 403
   - 管理员把自己降权(去掉 platform_admin)→ 400
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
try:
    _TMP_DIR = _REPO_ROOT / ".tmp-test-multi-role-migration"
    _TMP_DIR.mkdir(exist_ok=True)
except OSError:  # pragma: no cover - 只读工作区
    _TMP_DIR = Path(tempfile.mkdtemp(prefix="xiulijiu-multi-role-migration-"))
DB_PATH = _TMP_DIR / "legacy.db"
if DB_PATH.exists():
    DB_PATH.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"
os.environ["SMS_PROVIDER"] = "debug"
os.environ["SMS_DEBUG_CODE"] = "246810"
os.environ["PAYMENT_ALLOW_MOCK"] = "true"
sys.path.insert(0, str(_REPO_ROOT))

import sqlite3  # noqa: E402

from app.core.auth import make_token  # noqa: E402
from app.core.database import async_session, init_db  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

LEGACY_ROWS = [
    # (id, phone, name, role, business_role)
    (8001, "19900008001", "老客户", "CUSTOMER", "customer"),
    (8002, "19900008002", "老店长", "ADMIN", "store_manager"),
    (8003, "19900008003", "老师傅", "REPAIRER", "repairer"),
    (8004, "19900008004", "老管理员", "ADMIN", "platform_admin"),
]


def _seed_legacy_schema() -> None:
    """手工造出「老结构」的 users 表(不含多角色列)。"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone VARCHAR(20) NOT NULL,
            name VARCHAR(50) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'CUSTOMER',
            business_role VARCHAR(30) NOT NULL DEFAULT 'customer',
            avatar VARCHAR(500),
            created_at DATETIME,
            updated_at DATETIME
        )
        """
    )
    cur.executemany(
        "INSERT INTO users (id, phone, name, role, business_role, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, '2026-01-01 00:00:00', '2026-01-01 00:00:00')",
        LEGACY_ROWS,
    )
    conn.commit()
    conn.close()


def _read_columns() -> set[str]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    columns = {row[1] for row in cur.execute("PRAGMA table_info(users)")}
    conn.close()
    return columns


def _read_roles(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    row = cur.execute(
        "SELECT business_role, business_roles, active_business_role FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return row


def main_sync() -> int:
    results: list[tuple[str, bool, str]] = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
        print(("OK  " if ok else "FAIL") + f" {name:48s} {detail}")

    # === 1. 迁移:老结构 → 新结构 ===
    _seed_legacy_schema()
    before_columns = _read_columns()
    check("legacy_has_no_business_roles", "business_roles" not in before_columns, str(sorted(before_columns)))

    asyncio.run(init_db())
    # 再跑一次验证幂等
    asyncio.run(init_db())

    after_columns = _read_columns()
    check("migration_adds_business_roles", "business_roles" in after_columns, "")
    check("migration_adds_active_role", "active_business_role" in after_columns, "")

    for user_id, expected in ((8001, "customer"), (8002, "store_manager"), (8003, "repairer"), (8004, "platform_admin")):
        row = _read_roles(user_id)
        check(
            f"backfill_{user_id}_roles",
            row is not None and row[1] in (f'["{expected}"]', [expected]),
            f"stored={row[1] if row else None}",
        )
        check(
            f"backfill_{user_id}_active",
            row is not None and row[2] == expected,
            f"active={row[2] if row else None}",
        )

    # 迁移后:老管理员依旧是管理员(并集判断读 business_roles)
    client = TestClient(app)
    admin_token = make_token(8004, "admin")
    staff_token = make_token(8002, "admin")
    customer_token = make_token(8001, "customer")
    repairer_token = make_token(8003, "repairer")
    admin_h = {"Authorization": f"Bearer {admin_token}"}
    staff_h = {"Authorization": f"Bearer {staff_token}"}
    customer_h = {"Authorization": f"Bearer {customer_token}"}
    repairer_h = {"Authorization": f"Bearer {repairer_token}"}

    r = client.get("/api/v1/users?limit=1", headers=admin_h)
    check("migrated_admin_still_admin", r.status_code == 200, f"status={r.status_code}")
    r = client.get("/api/v1/users?limit=1", headers=staff_h)
    check("migrated_store_manager_is_staff", r.status_code == 200, f"status={r.status_code}")
    r = client.get("/api/v1/users?limit=1", headers=repairer_h)
    check("migrated_repairer_not_staff", r.status_code == 403, f"status={r.status_code}")

    r = client.get("/api/v1/auth/me", headers=staff_h)
    if r.status_code == 200:
        body = r.json()
        check("migrated_me_has_roles", body.get("business_roles") == ["store_manager"], str(body.get("business_roles")))
        check("migrated_me_active", body.get("active_business_role") == "store_manager", str(body.get("active_business_role")))

    # === 2. 越权边界 ===
    r = client.patch("/api/v1/users/8001", json={"business_roles": ["platform_admin"]}, headers=customer_h)
    check("self_role_escalation_403", r.status_code == 403, f"status={r.status_code}")

    r = client.patch("/api/v1/users/8003/roles", json={"business_roles": ["platform_admin"]}, headers=customer_h)
    check("customer_assign_roles_403", r.status_code == 403, f"status={r.status_code}")

    r = client.patch("/api/v1/users/8001/roles", json={"business_roles": ["platform_admin"]}, headers=staff_h)
    check("store_manager_assign_roles_403", r.status_code == 403, f"status={r.status_code}")

    r = client.post(
        "/api/v1/users/8003/switch-active-role",
        json={"business_role": "store_manager"},
        headers=repairer_h,
    )
    check("switch_unheld_role_403", r.status_code == 403, f"status={r.status_code}")

    r = client.patch("/api/v1/users/8004/roles", json={"business_roles": ["repairer"]}, headers=admin_h)
    check("admin_self_demote_400", r.status_code == 400, f"status={r.status_code}")

    r = client.patch("/api/v1/users/8004/roles", json={"business_roles": []}, headers=admin_h)
    check("empty_roles_rejected", r.status_code in (400, 422), f"status={r.status_code}")

    # 管理员正常配置:老客户 → 店长+师傅+业务(目标场景)
    r = client.patch(
        "/api/v1/users/8001/roles",
        json={"business_roles": ["store_manager", "repairer", "promotion_manager"]},
        headers=admin_h,
    )
    check("admin_assign_three_roles_200", r.status_code == 200, f"status={r.status_code} {r.text[:140]}")
    if r.status_code == 200:
        body = r.json()
        check("assigned_three_roles", body["business_roles"] == ["store_manager", "repairer", "promotion_manager"], str(body["business_roles"]))
        check("assigned_active_is_workbench", body["active_business_role"] == "store_manager", str(body["active_business_role"]))
        check("assigned_history_has_grant", any(item["action"] == "grant" for item in body["history"]), str(body["history"])[:120])

    # 该客户现在有内部角色 → 能读用户名单
    r = client.get("/api/v1/users?limit=1", headers=customer_h)
    check("upgraded_user_now_staff", r.status_code == 200, f"status={r.status_code}")

    # 收回角色后立即失去内部权限
    r = client.patch("/api/v1/users/8001/roles", json={"business_roles": ["customer"]}, headers=admin_h)
    check("admin_revoke_200", r.status_code == 200, f"status={r.status_code}")
    r = client.get("/api/v1/users?limit=1", headers=customer_h)
    check("revoked_user_loses_staff", r.status_code == 403, f"status={r.status_code}")

    print("---")
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main_sync())
