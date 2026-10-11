"""订单级鉴权回归测试(2026-10-06)。

背景:2026-10-06 给订单加了「只能看自己的单」的守卫 `_require_order_visible`,
但它为了查师傅档案归属改成了 async,而 10 个调用点**漏了 await** ——
协程被静默丢弃,守卫生效为 0,导致**客户能读并修改他人订单**。
当时的完整回归测试(125 项)全绿,因为没有针对跨用户访问的用例。

本文件锁死这条边界,顺便覆盖:
- 客户 A 读/写客户 B 的订单 → 403(详情 / 日志 / 状态流转 / 服务单)
- 师傅读未指派给自己的订单 → 403
- 本人读自己的订单 → 200

运行:
    python tests/test_order_authz.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

TEMP_DIR = tempfile.TemporaryDirectory(prefix="xiulijiu-authz-")
DB_PATH = Path(TEMP_DIR.name) / "authz.db"
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

PASSED = 0
FAILED = 0


def expect_eq(label: str, got, want) -> None:
    global PASSED, FAILED
    if got == want:
        PASSED += 1
        print(f"  OK   {label} = {got}")
    else:
        FAILED += 1
        print(f"  FAIL {label} = {got}(期望 {want})")


def expect_true(label: str, cond: bool, detail: str = "") -> None:
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
        region = Region(name="回归区", level=2)
        db.add(region)
        await db.commit()
        await db.refresh(region)

        customer_a = User(phone="19911110001", name="客户A", role=UserRole.CUSTOMER,
                          business_role=BusinessRole.CUSTOMER.value)
        customer_b = User(phone="19911110002", name="客户B", role=UserRole.CUSTOMER,
                          business_role=BusinessRole.CUSTOMER.value)
        repairer_user = User(phone="19911110003", name="师傅C", role=UserRole.REPAIRER,
                             business_role=BusinessRole.REPAIRER.value)
        db.add_all([customer_a, customer_b, repairer_user])
        await db.commit()
        for u in (customer_a, customer_b, repairer_user):
            await db.refresh(u)

        other_repairer = Repairer(user_id=repairer_user.id, skills="general", status="online")
        db.add(other_repairer)
        await db.commit()
        await db.refresh(other_repairer)

        order_b = Order(customer_id=customer_b.id, source=OrderSource.REPAIR,
                        status=OrderStatus.CREATED, region_id=region.id, category="other",
                        description="B 的订单", address="某地",
                        customer_name_snapshot="客户B", customer_phone_snapshot="19911110002")
        order_a = Order(customer_id=customer_a.id, source=OrderSource.REPAIR,
                        status=OrderStatus.CREATED, region_id=region.id, category="other",
                        description="A 的订单", address="某地",
                        customer_name_snapshot="客户A", customer_phone_snapshot="19911110001")
        db.add_all([order_b, order_a])
        await db.commit()
        await db.refresh(order_b)
        await db.refresh(order_a)

        return {
            "a": customer_a.id, "b": customer_b.id,
            "repairer_user": repairer_user.id, "repairer": other_repairer.id,
            "order_a": order_a.id, "order_b": order_b.id,
        }


def main() -> int:
    ids = asyncio.run(seed())
    print(f"seed: {ids}")

    tok_a = make_token(ids["a"], "customer")
    hdr_a = {"Authorization": f"Bearer {tok_a}"}
    tok_rep = make_token(ids["repairer_user"], "repairer")
    hdr_rep = {"Authorization": f"Bearer {tok_rep}"}
    order_b = ids["order_b"]
    order_a = ids["order_a"]

    with TestClient(app) as client:
        print("\n=== 客户 A 访问客户 B 的订单:必须 403 ===")
        # 这几条就是当初漏 await 时全部返回 200 的路径
        expect_eq("GET   /orders/{B}", client.get(f"/api/v1/orders/{order_b}", headers=hdr_a).status_code, 403)
        expect_eq("GET   /orders/{B}/logs", client.get(f"/api/v1/orders/{order_b}/logs", headers=hdr_a).status_code, 403)
        expect_eq("POST  /orders/{B}/transition",
                  client.post(f"/api/v1/orders/{order_b}/transition",
                              json={"to_status": "cancelled", "operator_type": "customer"},
                              headers=hdr_a).status_code, 403)
        expect_eq("PATCH /orders/{B}",
                  client.patch(f"/api/v1/orders/{order_b}", json={"price": 1}, headers=hdr_a).status_code, 403)
        expect_eq("GET   /orders/{B}/service-bill/latest",
                  client.get(f"/api/v1/orders/{order_b}/service-bill/latest", headers=hdr_a).status_code, 403)
        expect_eq("POST  /orders/{B}/service-bill/confirm",
                  client.post(f"/api/v1/orders/{order_b}/service-bill/confirm", headers=hdr_a).status_code, 403)
        expect_eq("POST  /orders/{B}/rating",
                  client.post(f"/api/v1/orders/{order_b}/rating", json={"rating": 5}, headers=hdr_a).status_code, 403)

        print("\n=== 师傅访问未指派给自己的订单:必须 403 ===")
        expect_eq("GET  /orders/{B}(师傅)", client.get(f"/api/v1/orders/{order_b}", headers=hdr_rep).status_code, 403)
        expect_eq("POST /orders/{B}/service-bill(师傅)",
                  client.post(f"/api/v1/orders/{order_b}/service-bill",
                              json={"repairer_id": ids["repairer"], "items_json": "[]", "amount": 1,
                                    "warranty_days": 1, "confirmation_method": "phone"},
                              headers=hdr_rep).status_code, 403)

        print("\n=== 本人访问自己的订单:必须放行 ===")
        expect_eq("GET /orders/{A}(客户A)", client.get(f"/api/v1/orders/{order_a}", headers=hdr_a).status_code, 200)
        expect_eq("GET /orders/{A}/logs", client.get(f"/api/v1/orders/{order_a}/logs", headers=hdr_a).status_code, 200)

        print("\n=== 未登录:必须 401 ===")
        expect_eq("GET /orders/{A} 无 token", client.get(f"/api/v1/orders/{order_a}").status_code, 401)

        print("\n=== 订单列表数据范围 ===")
        listed = client.get(f"/api/v1/orders?limit=100", headers=hdr_a)
        expect_eq("GET /orders 列表", listed.status_code, 200)
        if listed.status_code == 200:
            rows = listed.json()
            expect_true("列表只含自己的单", all(o["customer_id"] == ids["a"] for o in rows),
                        f"共 {len(rows)} 条")
        expect_eq("GET /orders?customer_id=B(客户A)", 
                  client.get(f"/api/v1/orders?customer_id={ids['b']}", headers=hdr_a).status_code, 403)

    print(f"\n{PASSED}/{PASSED + FAILED} passed")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
