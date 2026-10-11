"""多角色(一个账号多个身份)回归测试 — 2026-10-07。

场景:18060936373 同时是 店长 + 师傅 + 业务。

覆盖:
- 登录/GET /auth/me 返回 business_roles 集合 + active_business_role
- GET /api/v1/users/{id}/roles 返回全部角色与当前选中角色
- 管理员 PATCH /api/v1/users/{id}/roles 可配置多角色(并写 user_role_grants 审计)
- 非管理员不能给自己加角色(越权防护)
- 管理员不能摘掉自己的 platform_admin(防自锁)
- 用户 POST /switch-active-role 只能在已拥有角色里选,选不拥有的角色 → 403
- 权限按「并集」:任一角色满足即放行(只选师傅身份时,店长接口仍可访问)
- 老接口 PATCH /users/{id} 传单个 business_role 时不再抹掉其它角色
"""
import os
import sys
import tempfile
from pathlib import Path

# 优先用工程内临时目录:DSH 沙箱下系统 temp 可能不可写。
# 工程目录只读时(CI)退回系统临时目录。
_REPO_ROOT = Path(__file__).resolve().parents[1]
try:
    _TMP_DIR = _REPO_ROOT / ".tmp-test-multi-role"
    _TMP_DIR.mkdir(exist_ok=True)
except OSError:  # pragma: no cover - 只读工作区
    _TMP_DIR = Path(tempfile.mkdtemp(prefix="xiulijiu-multi-role-"))
DB_PATH = _TMP_DIR / "multi_role.db"
if DB_PATH.exists():
    DB_PATH.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"
os.environ["SMS_PROVIDER"] = "debug"
os.environ["SMS_DEBUG_CODE"] = "246810"
os.environ["PAYMENT_ALLOW_MOCK"] = "true"
sys.path.insert(0, str(_REPO_ROOT))

import asyncio  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.core.auth import make_token  # noqa: E402
from app.core.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

ADMIN_ID = 9101
MULTI_ID = 9102
REPAIRER_ID = 9103

# 目标场景:一个号同时是店长 + 师傅 + 业务
MULTI_ROLES = ["store_manager", "repairer", "promotion_manager"]


async def _setup_users():
    from sqlalchemy import select

    from app.core.database import async_session
    from app.models.user import BusinessRole, User, UserRole
    from app.models.wallet import Wallet

    await init_db()
    async with async_session() as db:
        seed = [
            (ADMIN_ID, BusinessRole.PLATFORM_ADMIN, UserRole.ADMIN, ["platform_admin"]),
            (MULTI_ID, BusinessRole.STORE_MANAGER, UserRole.ADMIN, MULTI_ROLES),
            (REPAIRER_ID, BusinessRole.REPAIRER, UserRole.REPAIRER, ["repairer"]),
        ]
        for uid, primary, legacy, roles in seed:
            existing = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
            if existing:
                continue
            user = User(
                id=uid,
                phone=f"180{uid:08d}"[:11],
                name=f"user{uid}",
                role=legacy,
                business_role=primary.value,
                business_roles=roles,
                active_business_role=roles[0],
            )
            db.add(user)
            db.add(Wallet(user_id=uid))
        await db.commit()


def main_sync() -> int:
    asyncio.run(_setup_users())

    admin_token = make_token(ADMIN_ID, "admin")
    multi_token = make_token(MULTI_ID, "admin")
    repairer_token = make_token(REPAIRER_ID, "repairer")
    admin_h = {"Authorization": f"Bearer {admin_token}"}
    multi_h = {"Authorization": f"Bearer {multi_token}"}
    repairer_h = {"Authorization": f"Bearer {repairer_token}"}

    client = TestClient(app)
    results: list[tuple[str, bool, str]] = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))
        print(("OK  " if ok else "FAIL") + f" {name:52s} {detail}")

    # === 1. 角色字典 ===
    r = client.get("/api/v1/users/roles/options", headers=repairer_h)
    check("role_options_200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        values = {item["value"] for item in r.json()}
        check(
            "role_options_cover_all",
            {"customer", "repairer", "store_manager", "promotion_manager"} <= values,
            str(sorted(values)),
        )

    # === 2. 多角色账号读出角色集合 ===
    r = client.get(f"/api/v1/users/{MULTI_ID}/roles", headers=multi_h)
    check("multi_self_roles_200", r.status_code == 200, f"status={r.status_code} {r.text[:120]}")
    if r.status_code == 200:
        body = r.json()
        check("multi_roles_all_returned", body["business_roles"] == MULTI_ROLES, str(body["business_roles"]))
        check("multi_active_role", body["active_business_role"] == "store_manager", body["active_business_role"])
        check("multi_can_switch", body["can_switch"] is True, str(body["can_switch"]))
        check(
            "multi_workbench_roles",
            set(body["workbench_roles"]) == set(MULTI_ROLES),
            str(body["workbench_roles"]),
        )

    # 单角色账号:不能切换
    r = client.get(f"/api/v1/users/{REPAIRER_ID}/roles", headers=repairer_h)
    if r.status_code == 200:
        check("single_role_cannot_switch", r.json()["can_switch"] is False, str(r.json()))

    # 客户自己看自己的角色(repairer 看别人 → 403)
    r = client.get(f"/api/v1/users/{MULTI_ID}/roles", headers=repairer_h)
    check("other_user_roles_403", r.status_code == 403, f"status={r.status_code}")

    # === 3. /auth/me 带角色集合 ===
    r = client.get("/api/v1/auth/me", headers=multi_h)
    check("me_200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        body = r.json()
        check("me_business_roles", body.get("business_roles") == MULTI_ROLES, str(body.get("business_roles")))
        check(
            "me_active_business_role",
            body.get("active_business_role") == "store_manager",
            str(body.get("active_business_role")),
        )

    # === 4. 权限并集:当前是店长,但更早的师傅身份同样放行 ===
    # /api/v1/users 需要 staff 角色(店长/城市/客服/财务/二接/管理员)
    r = client.get("/api/v1/users?limit=1", headers=multi_h)
    check("staff_union_users_200", r.status_code == 200, f"status={r.status_code}")
    r = client.get("/api/v1/users?limit=1", headers=repairer_h)
    check("repairer_not_staff_403", r.status_code == 403, f"status={r.status_code}")

    # 切换到师傅身份后,店长/经理类接口仍然可用(并集语义)
    r = client.post(
        f"/api/v1/users/{MULTI_ID}/switch-active-role",
        json={"business_role": "repairer"},
        headers=multi_h,
    )
    check("switch_to_repairer_200", r.status_code == 200, f"status={r.status_code} {r.text[:120]}")
    if r.status_code == 200:
        check(
            "switch_updates_active",
            r.json()["active_business_role"] == "repairer",
            r.json()["active_business_role"],
        )
        check(
            "switch_keeps_all_roles",
            r.json()["business_roles"] == MULTI_ROLES,
            str(r.json()["business_roles"]),
        )

    r = client.get("/api/v1/users?limit=1", headers=multi_h)
    check("staff_still_200_after_switch", r.status_code == 200, f"status={r.status_code}")

    r = client.get("/api/v1/auth/me", headers=multi_h)
    if r.status_code == 200:
        check("me_reflects_switch", r.json().get("active_business_role") == "repairer",
              str(r.json().get("active_business_role")))

    # 切成自己没有的角色 → 403
    r = client.post(
        f"/api/v1/users/{REPAIRER_ID}/switch-active-role",
        json={"business_role": "platform_admin"},
        headers=repairer_h,
    )
    check("switch_to_unheld_role_403", r.status_code == 403, f"status={r.status_code}")

    # === 5. 管理员配置多角色 ===
    r = client.patch(
        f"/api/v1/users/{REPAIRER_ID}/roles",
        json={"business_roles": ["repairer", "store_manager"], "remark": "兼任门店店长"},
        headers=multi_h,
    )
    check("non_admin_assign_403", r.status_code == 403, f"status={r.status_code}")

    r = client.patch(
        f"/api/v1/users/{REPAIRER_ID}/roles",
        json={"business_roles": ["repairer", "store_manager"], "remark": "兼任门店店长"},
        headers=admin_h,
    )
    check("admin_assign_200", r.status_code == 200, f"status={r.status_code} {r.text[:160]}")
    if r.status_code == 200:
        body = r.json()
        check(
            "admin_assign_roles_saved",
            set(body["business_roles"]) == {"repairer", "store_manager"},
            str(body["business_roles"]),
        )
        check("admin_assign_history", len(body["history"]) >= 1, f"history={len(body['history'])}")

    # 普通用户现在能切换了
    r = client.get(f"/api/v1/users/{REPAIRER_ID}/roles", headers=repairer_h)
    if r.status_code == 200:
        check("assigned_user_can_switch", r.json()["can_switch"] is True, str(r.json()["can_switch"]))

    # 该用户切换成店长后,token 里的 business_role 兼容字段同步
    r = client.post(
        f"/api/v1/users/{REPAIRER_ID}/switch-active-role",
        json={"business_role": "store_manager"},
        headers=repairer_h,
    )
    check("assigned_switch_200", r.status_code == 200, f"status={r.status_code} {r.text[:120]}")
    r = client.get(f"/api/v1/users/{REPAIRER_ID}", headers=repairer_h)
    if r.status_code == 200:
        check("legacy_business_role_synced", r.json()["business_role"] == "repairer",
              r.json()["business_role"])

    # === 6. 越权防护:不能自己改自己的角色集合 ===
    r = client.patch(
        f"/api/v1/users/{MULTI_ID}",
        json={"business_roles": ["platform_admin"]},
        headers=multi_h,
    )
    check("self_escalation_403", r.status_code == 403, f"status={r.status_code}")

    # 老接口单角色写法:叠加而不是覆盖(保留 store_manager + promotion_manager)
    r = client.patch(
        f"/api/v1/users/{REPAIRER_ID}",
        json={"business_role": "customer"},
        headers=admin_h,
    )
    check("legacy_patch_200", r.status_code == 200, f"status={r.status_code} {r.text[:160]}")
    if r.status_code == 200:
        roles = set(r.json().get("business_roles") or [])
        check("legacy_patch_keeps_roles", {"repairer", "store_manager"} <= roles, str(sorted(roles)))
        check("legacy_patch_adds_role", "customer" in roles, str(sorted(roles)))

    # === 7. 管理员不能摘掉自己的 platform_admin ===
    r = client.patch(
        f"/api/v1/users/{ADMIN_ID}/roles",
        json={"business_roles": ["store_manager"]},
        headers=admin_h,
    )
    check("admin_self_lockout_400", r.status_code == 400, f"status={r.status_code}")

    # === 8. 管理员给一个账号配三个角色(目标场景 18060936373) ===
    r = client.patch(
        f"/api/v1/users/{MULTI_ID}/roles",
        json={"business_roles": MULTI_ROLES, "active_business_role": "promotion_manager"},
        headers=admin_h,
    )
    check("admin_set_three_roles_200", r.status_code == 200, f"status={r.status_code} {r.text[:160]}")
    if r.status_code == 200:
        body = r.json()
        check("three_roles_saved", body["business_roles"] == MULTI_ROLES, str(body["business_roles"]))
        check("three_roles_active", body["active_business_role"] == "promotion_manager",
              body["active_business_role"])
        check(
            "three_roles_labels",
            body["role_labels"] == ["店长", "师傅", "业务"],
            str(body["role_labels"]),
        )

    r = client.get("/api/v1/auth/me", headers=multi_h)
    if r.status_code == 200:
        check("login_payload_three_roles", r.json().get("business_roles") == MULTI_ROLES,
              str(r.json().get("business_roles")))

    print("---")
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main_sync())
