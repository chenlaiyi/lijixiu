"""跨角色鉴权与合法路径回归测试(2026-10-06)。

与 `test_order_authz.py` 互补:
- `test_order_authz.py` 锁「订单级越权必须被拦」
- 本文件锁「**合法操作不能被误伤**」+ 其余模块的跨角色边界

起因:2026-10-06 修「师傅端工单列表 403」时,把订单守卫改成 async 却漏了 await,
导致守卫静默失效(客户可读写他人订单)。修完后又必须确认没把合法路径一起挡掉 -
上一轮的教训就是「修 A 容易坏 B」。

覆盖:
1. 师傅接自己的单 → 放行;别的师傅接同一单 → 403
2. 师傅按档案 id 查工单(小程序实际用法) → 200;查他人档案 id → 403
3. 师傅给自己单提交服务单 → 不被 403
4. 客户读自己单 200 / 读他人单 403
5. 钱包:本人 200、他人 403、提现列表仅平台管理员(店长也 403)、为他人申请提现 403
6. 内部角色可读全量数据(店长读他人订单 200)
7. 客户不能读内部数据(工资单 / 用户名单 / 分配审计 / 告警)
8. 客户能读自己的地址 / 保修 / 家政

运行:
    python tests/test_role_boundaries.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

TEMP_DIR = tempfile.TemporaryDirectory(prefix="xiulijiu-roles-")
DB_PATH = Path(TEMP_DIR.name) / "roles.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"
os.environ["SMS_PROVIDER"] = "debug"
os.environ["SMS_DEBUG_CODE"] = "246810"
os.environ["ALLOW_SMS_DEBUG_ENDPOINT"] = "true"
os.environ["PAYMENT_ALLOW_MOCK"] = "true"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.auth import make_token  # noqa: E402
from app.core.database import async_session, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.order import Order, OrderSource, OrderStatus  # noqa: E402
from app.models.region import Region  # noqa: E402
from app.models.repairer import Repairer  # noqa: E402
from app.models.user import BusinessRole, User, UserRole  # noqa: E402
from app.models.wallet import Wallet  # noqa: E402

PASSED = 0
FAILED = 0


def chk(label: str, cond: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  OK   {label}" + (f" — {detail}" if detail else ""))
    else:
        FAILED += 1
        print(f"  FAIL {label} — {detail}")


async def seed() -> dict:
    await init_db()
    async with async_session() as db:
        region = Region(name="边界区", level=2)
        db.add(region)
        await db.commit()
        await db.refresh(region)

        cust = User(phone="19933330001", name="客户", role=UserRole.CUSTOMER,
                    business_role=BusinessRole.CUSTOMER.value)
        cust2 = User(phone="19933330002", name="另一客户", role=UserRole.CUSTOMER,
                     business_role=BusinessRole.CUSTOMER.value)
        rep_user = User(phone="19933330003", name="师傅", role=UserRole.REPAIRER,
                        business_role=BusinessRole.REPAIRER.value)
        rep_user2 = User(phone="19933330004", name="别的师傅", role=UserRole.REPAIRER,
                         business_role=BusinessRole.REPAIRER.value)
        mgr = User(phone="19933330005", name="店长", role=UserRole.ADMIN,
                   business_role=BusinessRole.STORE_MANAGER.value)
        admin = User(phone="19933330006", name="总管理", role=UserRole.ADMIN,
                     business_role=BusinessRole.PLATFORM_ADMIN.value)
        db.add_all([cust, cust2, rep_user, rep_user2, mgr, admin])
        await db.commit()
        for u in (cust, cust2, rep_user, rep_user2, mgr, admin):
            await db.refresh(u)

        r1 = Repairer(user_id=rep_user.id, skills="plumbing", status="online")
        r2 = Repairer(user_id=rep_user2.id, skills="plumbing", status="online")
        db.add_all([r1, r2])
        await db.commit()
        await db.refresh(r1)
        await db.refresh(r2)

        o_assigned = Order(customer_id=cust.id, source=OrderSource.REPAIR,
                           status=OrderStatus.ASSIGNED, region_id=region.id, category="other",
                           description="指派给 r1", address="x",
                           repairer_id=r1.id, assigned_repairer_id=r1.id,
                           customer_name_snapshot="客户", customer_phone_snapshot="19933330001")
        o_servicing = Order(customer_id=cust.id, source=OrderSource.REPAIR,
                            status=OrderStatus.SERVICING, region_id=region.id, category="other",
                            description="服务中", address="x",
                            repairer_id=r1.id, assigned_repairer_id=r1.id,
                            customer_name_snapshot="客户", customer_phone_snapshot="19933330001")
        o_mine = Order(customer_id=cust.id, source=OrderSource.REPAIR,
                       status=OrderStatus.WAIT_PAYMENT, region_id=region.id, category="other",
                       description="我的待支付", address="x",
                       customer_name_snapshot="客户", customer_phone_snapshot="19933330001")
        o_other = Order(customer_id=cust2.id, source=OrderSource.REPAIR,
                        status=OrderStatus.CREATED, region_id=region.id, category="other",
                        description="别人的", address="x",
                        customer_name_snapshot="另一客户", customer_phone_snapshot="19933330002")
        db.add_all([o_assigned, o_servicing, o_mine, o_other])
        await db.commit()
        for o in (o_assigned, o_servicing, o_mine, o_other):
            await db.refresh(o)

        db.add_all([
            Wallet(user_id=cust.id, available_balance=100.0),
            Wallet(user_id=cust2.id, available_balance=50.0),
        ])
        await db.commit()

        return {
            "cust": cust.id, "cust2": cust2.id, "rep": rep_user.id, "rep2": rep_user2.id,
            "rep_profile": r1.id, "rep2_profile": r2.id, "mgr": mgr.id, "admin": admin.id,
            "o_assigned": o_assigned.id, "o_servicing": o_servicing.id,
            "o_mine": o_mine.id, "o_other": o_other.id,
        }


def hdr(uid: int, role: str) -> dict:
    return {"Authorization": f"Bearer {make_token(uid, role)}"}


def main() -> int:
    ids = asyncio.run(seed())
    cust = hdr(ids["cust"], "customer")
    cust2 = hdr(ids["cust2"], "customer")
    rep = hdr(ids["rep"], "repairer")
    rep2 = hdr(ids["rep2"], "repairer")
    mgr = hdr(ids["mgr"], "admin")
    admin = hdr(ids["admin"], "admin")

    with TestClient(app) as c:
        print("=== 师傅:合法接单 vs 越权接单 ===")
        r = c.post(f"/api/v1/orders/{ids['o_assigned']}/transition",
                   json={"to_status": "accepted", "operator_type": "repairer"}, headers=rep)
        chk("本人接自己的单不被拦", r.status_code != 403, f"status={r.status_code}")
        r = c.post(f"/api/v1/orders/{ids['o_assigned']}/transition",
                   json={"to_status": "accepted", "operator_type": "repairer"}, headers=rep2)
        chk("别的师傅接同一单被拦", r.status_code == 403, f"status={r.status_code}")

        print("\n=== 师傅工单列表:按档案 id(小程序用法)===")
        r = c.get(f"/api/v1/orders?assigned_repairer_id={ids['rep_profile']}&limit=100", headers=rep)
        chk("查自己档案 id 放行", r.status_code == 200, f"status={r.status_code}")
        r = c.get(f"/api/v1/orders?assigned_repairer_id={ids['rep2_profile']}&limit=100", headers=rep)
        chk("查他人档案 id 被拦", r.status_code == 403, f"status={r.status_code}")

        print("\n=== 师傅提交服务单:本人放行 / 他人 403 ===")
        r = c.post(f"/api/v1/orders/{ids['o_servicing']}/service-bill",
                   json={"repairer_id": ids["rep_profile"],
                         "items_json": '[{"name":"labor","quantity":1,"unit_price":10,"subtotal":10}]',
                         "amount": 10, "warranty_days": 30, "confirmation_method": "phone"},
                   headers=rep)
        chk("本人提交不被 403", r.status_code != 403, f"status={r.status_code} {r.text[:70]}")
        r = c.post(f"/api/v1/orders/{ids['o_servicing']}/service-bill",
                   json={"repairer_id": ids["rep_profile"], "items_json": "[]", "amount": 10,
                         "warranty_days": 30, "confirmation_method": "phone"},
                   headers=rep2)
        chk("他人提交被拦", r.status_code == 403, f"status={r.status_code}")

        print("\n=== 客户订单边界 ===")
        chk("读自己单 200", c.get(f"/api/v1/orders/{ids['o_mine']}", headers=cust).status_code == 200)
        chk("读他人单 403", c.get(f"/api/v1/orders/{ids['o_other']}", headers=cust).status_code == 403)

        print("\n=== 钱包边界 ===")
        chk("本人余额 200", c.get(f"/api/v1/wallet/balance/{ids['cust']}", headers=cust).status_code == 200)
        chk("他人余额 403", c.get(f"/api/v1/wallet/balance/{ids['cust2']}", headers=cust).status_code == 403)
        # 2026-10-07:小程序「收益」页要读自己的提现记录,原来收成 admin-only 会让该页恒为空。
        # 现在与 /balance、/ledger 一致:本人读自己、内部角色读全部。
        chk("客户读提现列表 200(收益页需要)",
            c.get("/api/v1/wallet/withdrawals", headers=cust).status_code == 200)
        chk("客户读自己的提现记录 200",
            c.get(f"/api/v1/wallet/withdrawals?user_id={ids['cust']}", headers=cust).status_code == 200)
        chk("客户读他人的提现记录 403",
            c.get(f"/api/v1/wallet/withdrawals?user_id={ids['cust2']}", headers=cust).status_code == 403)
        chk("店长读提现列表 200(内部角色)",
            c.get("/api/v1/wallet/withdrawals", headers=mgr).status_code == 200)
        chk("平台管理员读提现列表 200",
            c.get("/api/v1/wallet/withdrawals", headers=admin).status_code == 200)
        chk("客户为他人申请提现 403",
            c.post(f"/api/v1/wallet/withdraw/{ids['cust2']}", json={"amount": 1},
                   headers=cust).status_code == 403)

        print("\n=== 内部角色数据范围 ===")
        chk("店长读全量订单 200", c.get("/api/v1/orders?limit=100", headers=mgr).status_code == 200)
        chk("店长读他人订单详情 200",
            c.get(f"/api/v1/orders/{ids['o_other']}", headers=mgr).status_code == 200)

        print("\n=== 客户不得读内部数据 ===")
        for path in ("/api/v1/business/payroll", "/api/v1/users?limit=5",
                     "/api/v1/service-areas/assignment-logs", "/api/v1/admin/alerts"):
            r = c.get(path, headers=cust)
            chk(f"{path} -> 403", r.status_code == 403, f"status={r.status_code}")

        print("\n=== 客户可读自己的数据 ===")
        chk("地址簿 200",
            c.get(f"/api/v1/business/addresses?user_id={ids['cust']}", headers=cust).status_code == 200)
        chk("保修凭证 200", c.get("/api/v1/business/warranties", headers=cust).status_code == 200)
        chk("家政需求 200", c.get("/api/v1/business/domestic/demands", headers=cust).status_code == 200)

        print("\n=== 未登录 ===")
        chk("无 token 读订单 401", c.get(f"/api/v1/orders/{ids['o_mine']}").status_code == 401)

    print(f"\n{PASSED}/{PASSED + FAILED} passed")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
