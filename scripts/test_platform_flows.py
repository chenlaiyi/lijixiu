"""Isolated end-to-end checks for the platform's critical business flows."""

from __future__ import annotations

import os
import tempfile
import json
import sqlite3
import sys
from pathlib import Path


TEMP_DIR = tempfile.TemporaryDirectory(prefix="xiulijiu-flow-")
DB_PATH = Path(TEMP_DIR.name) / "flow.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"
os.environ["SMS_PROVIDER"] = "debug"
os.environ["SMS_DEBUG_CODE"] = "246810"
os.environ["PAYMENT_ALLOW_MOCK"] = "true"
os.environ["WECHAT_REVIEW_ACCOUNT"] = "reviewer"
REVIEW_PASSWORD = os.environ.setdefault("WECHAT_REVIEW_PASSWORD", "local-test-review-pass")
os.environ["WECHAT_REVIEW_PHONE"] = "18800000999"
os.environ["WECHAT_REVIEW_MIN_BALANCE"] = "100"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.models.pay_order import PayProvider  # noqa: E402
from app.schemas.payment import PayCreateRequest  # noqa: E402
from app.services import wechat_pay  # noqa: E402
from app.services.wechat_pay import WeChatPayError, WeChatPaymentIntent  # noqa: E402


def expect(response, label: str):
    if response.status_code >= 400:
        raise AssertionError(f"{label}: {response.status_code} {response.text}")
    return response.json()


def hdr(token: str) -> dict:
    """Auth header helper for protected endpoints (2026-08-09 P0 鉴权后必传)。"""
    return {"Authorization": f"Bearer {token}"}


def demo_login(client: TestClient, phone: str, name: str):
    """返回完整响应 {token, user},方便 caller 同时拿 token + user。"""
    return expect(
        client.post(
            "/api/v1/auth/wechat-login",
            json={"code": f"{phone}:{name}:customer"},
        ),
        f"login {phone}",
    )


def advance_to_service(client: TestClient, order: dict, manager: dict) -> tuple[dict, int]:
    order = expect(
        client.post(
            f"/api/v1/orders/{order['id']}/self-service",
            json={"manager_id": manager["id"], "skills": "general service"},
        ),
        "manager self service",
    )
    repairer_id = order["assigned_repairer_id"]
    order = expect(
        client.post(
            f"/api/v1/orders/{order['id']}/transition",
            json={
                "to_status": "repairer_accepted",
                "operator_type": "repairer",
                "operator_id": manager["id"],
            },
        ),
        "repairer accepts",
    )
    order = expect(
        client.post(
            f"/api/v1/orders/{order['id']}/transition",
            json={
                "to_status": "servicing",
                "operator_type": "repairer",
                "operator_id": manager["id"],
            },
        ),
        "service starts",
    )
    return order, repairer_id


def create_bill(client: TestClient, order_id: int, repairer_id: int, amount: float):
    bill = expect(
        client.post(
            f"/api/v1/orders/{order_id}/service-bill",
            json={
                "repairer_id": repairer_id,
                "items_json": json.dumps([
                    {"name": "labor", "quantity": 1, "unit_price": amount, "subtotal": amount}
                ]),
                "amount": amount,
                "warranty_days": 30,
                "confirmation_method": "phone",
                "confirmation_note": "confirmed by phone",
            },
        ),
        "service bill",
    )
    assert bill["status"] == "submitted"
    return bill


def mock_pay(client: TestClient, order_id: int, payer_id: int, amount: float, tx: str):
    payment = expect(
        client.post(
            "/api/v1/payment/create",
            json={
                "order_id": order_id,
                "user_id": payer_id,
                "amount": amount,
                "provider": "mock",
            },
        ),
        "create payment",
    )
    return expect(
        client.post(
            "/api/v1/payment/callback",
            json={"pay_order_id": payment["pay_order_id"], "transaction_id": tx},
        ),
        "payment callback",
    )


def run() -> None:
    with TestClient(app) as client:
        # 2026-08-09:login 返回完整响应,分开存 user 和 token,
        # 后面所有受保护端点都要带 headers=hdr(token)
        logins = {
            "admin": demo_login(client, "18800000000", "admin"),
            "customer": demo_login(client, "18800000001", "customer"),
            "repairer": demo_login(client, "18800000002", "repairer"),
            "manager": demo_login(client, "18800000004", "manager"),
            "city": demo_login(client, "18800000005", "city"),
            "promotion": demo_login(client, "18800000006", "promotion"),
            "support": demo_login(client, "18800000007", "support"),
            "finance": demo_login(client, "18800000008", "finance"),
        }
        users = {k: v["user"] for k, v in logins.items()}
        tokens = {k: v["token"] for k, v in logins.items()}
        assert users["manager"]["business_role"] == "store_manager"
        assert users["support"]["business_role"] == "tech_support"
        assert users["finance"]["business_role"] == "finance"

        review_login = expect(
            client.post(
                "/api/v1/auth/review-login",
                json={"account": "reviewer", "password": REVIEW_PASSWORD},
            ),
            "review login",
        )
        assert review_login["user"]["phone"] == "18800000999"
        assert review_login["user"]["business_role"] == "repairer"
        review_user_id = review_login["user"]["id"]
        review_token = review_login["token"]
        review_wallet = expect(
            client.get(
                f"/api/v1/wallet/balance/{review_user_id}",
                headers=hdr(review_token),
            ),
            "review wallet",
        )
        assert review_wallet["available_balance"] >= 100
        review_withdrawal = expect(
            client.post(
                f"/api/v1/wallet/withdraw/{review_user_id}",
                json={"amount": 5, "remark": "review account reset test"},
                headers=hdr(review_token),
            ),
            "review account withdrawal",
        )
        expect(
            client.post(
                "/api/v1/auth/review-login",
                json={"account": "reviewer", "password": REVIEW_PASSWORD},
            ),
            "review login reset",
        )
        reset_wallet = expect(
            client.get(
                f"/api/v1/wallet/balance/{review_user_id}",
                headers=hdr(review_token),
            ),
            "reset review wallet",
        )
        assert reset_wallet["available_balance"] >= 100
        assert reset_wallet["frozen_balance"] == 0
        reset_withdrawals = expect(
            client.get(
                f"/api/v1/wallet/withdrawals?user_id={review_user_id}",
                headers=hdr(tokens["admin"]),
            ),
            "reset review withdrawals",
        )
        assert next(item for item in reset_withdrawals if item["id"] == review_withdrawal["id"])["status"] == "rejected"
        assert client.post(
            "/api/v1/auth/review-login",
            json={"account": "reviewer", "password": "wrong-password"},
        ).status_code == 401

        rejected = client.post(
            "/api/v1/auth/wechat-login",
            json={"code": "13900000000:unsafe:customer"},
        )
        assert rejected.status_code == 403
        sms = expect(
            client.post("/api/v1/auth/sms/request", json={"phone": "13900000000"}),
            "request sms",
        )
        payer = expect(
            client.post(
                "/api/v1/auth/sms/login",
                json={
                    "phone": "13900000000",
                    "code": sms["debug_code"],
                    "name": "payer",
                },
            ),
            "sms login",
        )["user"]

        expect(
            client.patch(
                f"/api/v1/users/{users['customer']['id']}",
                json={"promotion_manager_id": users["promotion"]["id"]},
            ),
            "link promotion manager",
        )
        region = expect(
            client.post(
                "/api/v1/regions",
                json={"name": "Flow Region", "level": 3, "manager_id": users["city"]["id"]},
            ),
            "region",
        )
        store = expect(
            client.post(
                "/api/v1/stores",
                json={
                    "name": "Flow Store",
                    "region_id": region["id"],
                    "manager_id": users["manager"]["id"],
                    "city_manager_id": users["city"]["id"],
                },
            ),
            "store",
        )
        store = expect(
            client.patch(
                f"/api/v1/stores/{store['id']}",
                json={"status": "active", "enabled": True},
            ),
            "activate store",
        )
        area_data = expect(
            client.get("/api/v1/service-areas?district=思明区&limit=3"),
            "xiamen service areas",
        )
        assert area_data["total"] == 98
        area_ids = [item["id"] for item in area_data["items"]]
        assignment_body = {
            "service_area_ids": area_ids,
            "primary_store_id": store["id"],
            "manager_id": users["manager"]["id"],
            "conflict_mode": "replace",
            "operator_user_id": users["admin"]["id"],
            "remark": "flow test",
        }
        assignment_preview = expect(
            client.post(
                "/api/v1/service-areas/assignments/bulk",
                json={**assignment_body, "dry_run": True},
            ),
            "service area assignment preview",
        )
        assert assignment_preview["created"] == 3
        expect(
            client.post(
                "/api/v1/service-areas/assignments/bulk",
                json={**assignment_body, "dry_run": False},
            ),
            "service area assignment",
        )
        invalid_manager = client.post(
            "/api/v1/service-areas/assignments/bulk",
            json={
                "service_area_ids": [area_ids[0]],
                "manager_id": users["finance"]["id"],
                "conflict_mode": "replace",
            },
        )
        assert invalid_manager.status_code == 400
        matched_area = area_data["items"][0]
        standard_address = expect(
            client.post(
                "/api/v1/stores/addresses",
                json={
                    "service_area_id": matched_area["id"],
                    "store_id": store["id"],
                    "estate": "Flow Garden",
                    "building": "1 Building",
                    "unit": "1 Unit",
                    "room": "101",
                    "business_owner_user_id": users["promotion"]["id"],
                    "created_by_user_id": users["admin"]["id"],
                },
            ),
            "standard service address",
        )
        assert standard_address["address_code"].startswith("ADDR-")
        assert standard_address["full_address"].endswith("1Building-1Unit-101")
        duplicate_address = client.post(
            "/api/v1/stores/addresses",
            json={
                "service_area_id": matched_area["id"],
                "store_id": store["id"],
                "estate": "Flow Garden",
                "building": "1 Building",
                "unit": "1 Unit",
                "room": "101",
                "created_by_user_id": users["admin"]["id"],
            },
        )
        assert duplicate_address.status_code == 400
        unregistered_address_order = client.post(
            "/api/v1/orders",
            json={
                "customer_id": users["customer"]["id"],
                "region_id": region["id"],
                "category": "plumbing",
                "description": "Unregistered address must be blocked",
                "address": "Any free text address",
            },
        )
        assert unregistered_address_order.status_code == 400
        matched_order = expect(
            client.post(
                "/api/v1/orders",
                json={
                    "customer_id": users["customer"]["id"],
                    "region_id": region["id"],
                    "category": "plumbing",
                    "description": "Service area routing",
                    "address_book_id": standard_address["id"],
                    "address": "This client text must be ignored",
                    "contact_phone": users["customer"]["phone"],
                },
            ),
            "service area routed order",
        )
        assert matched_order["store_id"] == store["id"]
        assert matched_order["address"] == standard_address["full_address"]
        assert matched_order["address_code_snapshot"] == standard_address["address_code"]
        assert matched_order["address_owner_user_id"] == users["promotion"]["id"]
        assert matched_order["channel_manager_id_snapshot"] == users["promotion"]["id"]
        assert matched_order["service_area_name_snapshot"] == matched_area["name"]
        assert matched_order["service_area_manager_id"] == users["manager"]["id"]
        assignment_logs = expect(
            client.get("/api/v1/service-areas/assignment-logs?limit=10"),
            "service area assignment logs",
        )
        assert any(item["operator_user_id"] == users["admin"]["id"] for item in assignment_logs)
        expect(
            client.post(
                "/api/v1/business/addresses",
                json={
                    "user_id": users["customer"]["id"],
                    "contact_name": "customer",
                    "contact_phone": users["customer"]["phone"],
                    "service_address_id": standard_address["id"],
                    "is_default": True,
                },
            ),
            "customer address",
        )

        proxy_order = expect(
            client.post(
                "/api/v1/orders",
                json={
                    "customer_id": users["customer"]["id"],
                    "region_id": region["id"],
                    "store_id": store["id"],
                    "category": "plumbing",
                    "description": "Proxy repair",
                    "address_book_id": standard_address["id"],
                    "address": standard_address["full_address"],
                    "contact_phone": users["customer"]["phone"],
                    "created_by_user_id": users["manager"]["id"],
                    "proxy_creator_id": users["manager"]["id"],
                    "is_proxy_order": True,
                    "proxy_reason": "phone_request",
                },
            ),
            "proxy order",
        )
        proxy_order, repairer_id = advance_to_service(client, proxy_order, users["manager"])
        create_bill(client, proxy_order["id"], repairer_id, 200)
        assert PayCreateRequest(
            order_id=proxy_order["id"], user_id=payer["id"], amount=200
        ).provider == PayProvider.WECHAT
        original_exchange = wechat_pay.exchange_js_code
        original_create = wechat_pay.create_jsapi_payment
        wechat_pay.exchange_js_code = lambda _code: "test-openid"
        wechat_pay.create_jsapi_payment = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            WeChatPayError("merchant payment capability blocked")
        )
        failed_wechat = client.post(
            "/api/v1/payment/create",
            json={
                "order_id": proxy_order["id"],
                "user_id": payer["id"],
                "amount": 200,
                "js_code": "test-code",
            },
        )
        assert failed_wechat.status_code == 400
        failed_attempts = expect(
            client.get(f"/api/v1/payment/list?order_id={proxy_order['id']}&limit=10"),
            "failed wechat payment attempt",
        )
        assert failed_attempts[0]["provider"] == "wechat"
        assert failed_attempts[0]["status"] == "failed"
        wechat_pay.create_jsapi_payment = lambda pay_order, **_kwargs: WeChatPaymentIntent(
            pay_url=f"wechat://pay/{pay_order.id}",
            payment_params={
                "timeStamp": "1",
                "nonceStr": "test",
                "package": "prepay_id=test-prepay",
                "signType": "RSA",
                "paySign": "test-signature",
            },
            prepay_id="test-prepay",
            payer_openid="test-openid",
        )
        try:
            default_payment = expect(
                client.post(
                    "/api/v1/payment/create",
                    json={
                        "order_id": proxy_order["id"],
                        "user_id": payer["id"],
                        "amount": 200,
                        "js_code": "test-code",
                    },
                ),
                "default wechat payment",
            )
            assert default_payment["provider"] == "wechat"
            assert default_payment["payment_params"]["package"] == "prepay_id=test-prepay"
        finally:
            wechat_pay.exchange_js_code = original_exchange
            wechat_pay.create_jsapi_payment = original_create
        settings.PAYMENT_ALLOW_MOCK = False
        rejected_mock = client.post(
            "/api/v1/payment/create",
            json={
                "order_id": proxy_order["id"],
                "user_id": payer["id"],
                "amount": 200,
                "provider": "mock",
            },
        )
        assert rejected_mock.status_code == 400
        assert "模拟支付已关闭" in rejected_mock.text
        settings.PAYMENT_ALLOW_MOCK = True
        claim_code = expect(
            client.post(
                f"/api/v1/business/orders/{proxy_order['id']}/access/claim",
                json={"created_by_user_id": users["manager"]["id"]},
            ),
            "claim code",
        )
        pay_only = expect(
            client.post(
                "/api/v1/business/orders/claim",
                json={"token": claim_code["token"], "user_id": payer["id"]},
            ),
            "mismatched claim",
        )
        assert pay_only["action"] == "pay_only"
        claimed = expect(
            client.post(
                "/api/v1/business/orders/claim",
                json={"token": claim_code["token"], "user_id": users["customer"]["id"]},
            ),
            "customer claim",
        )
        assert claimed["action"] == "claimed"
        mock_pay(client, proxy_order["id"], payer["id"], 200, "proxy-pay")
        completed = expect(
            client.post(
                f"/api/v1/orders/{proxy_order['id']}/store-review?manager_id={users['manager']['id']}",
                json={
                    "technician_wage_amount": 80,
                    "wage_mode": "per_order",
                    "remark": "approved",
                },
            ),
            "store review",
        )
        assert completed["status"] == "completed"
        profits = expect(
            client.get(f"/api/v1/finance/profit/order/{proxy_order['id']}"),
            "proxy profits",
        )
        assert abs(profits["total_distributed"] - 200) < 0.01
        roles = {item["role_type"]: item for item in profits["items"]}
        assert roles["platform_retained"]["amount"] == 3
        assert roles["proxy_assist_reward"]["amount"] == 2
        assert roles["technician_wage"]["amount"] == 80
        assert roles["channel_manager_commission"]["user_id"] == users["promotion"]["id"]
        warranties = expect(
            client.get(
                f"/api/v1/business/warranties?customer_id={users['customer']['id']}"
            ),
            "warranties",
        )
        assert warranties and warranties[0]["amount"] == 200
        expired_warranty_id = warranties[0]["id"]
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                "UPDATE warranty_certificates SET expires_at=?, status='active' WHERE id=?",
                ("2000-01-01 00:00:00", expired_warranty_id),
            )
            conn.commit()
        finally:
            conn.close()
        active_warranties = expect(
            client.get(
                f"/api/v1/business/warranties?customer_id={users['customer']['id']}"
            ),
            "active warranties after expiration",
        )
        assert all(item["id"] != expired_warranty_id for item in active_warranties)
        warranty_history = expect(
            client.get(
                f"/api/v1/business/warranties?customer_id={users['customer']['id']}"
                "&include_expired=true"
            ),
            "warranty history",
        )
        expired_warranty = next(item for item in warranty_history if item["id"] == expired_warranty_id)
        assert expired_warranty["status"] == "expired"

        monthly_order = expect(
            client.post(
                "/api/v1/orders",
                json={
                    "customer_id": users["customer"]["id"],
                    "region_id": region["id"],
                    "store_id": store["id"],
                    "category": "electrical",
                    "description": "Monthly worker order",
                    "address_book_id": standard_address["id"],
                    "address": standard_address["full_address"],
                },
            ),
            "monthly order",
        )
        monthly_order, monthly_repairer = advance_to_service(client, monthly_order, users["manager"])
        create_bill(client, monthly_order["id"], monthly_repairer, 100)
        mock_pay(client, monthly_order["id"], users["customer"]["id"], 100, "monthly-pay")
        expect(
            client.post(
                f"/api/v1/orders/{monthly_order['id']}/store-review?manager_id={users['manager']['id']}",
                json={"technician_wage_amount": 0, "wage_mode": "monthly"},
            ),
            "monthly review",
        )
        wages = expect(
            client.get(f"/api/v1/business/wages?store_id={store['id']}&wage_mode=monthly"),
            "monthly wages",
        )
        assert wages and wages[0]["work_units"] == 1
        payroll = expect(
            client.post(
                "/api/v1/business/payroll",
                json={
                    "month": "2026-07",
                    "store_id": store["id"],
                    "manager_id": users["manager"]["id"],
                    "lines": [
                        {
                            "employee_user_id": users["manager"]["id"],
                            "amount": 10,
                            "remark": "flow payroll",
                        }
                    ],
                },
            ),
            "create payroll",
        )
        paid_payroll = expect(
            client.post(
                f"/api/v1/business/payroll/{payroll['period_id']}/pay",
                json={"store_id": store["id"], "manager_id": users["manager"]["id"]},
            ),
            "pay payroll",
        )
        assert paid_payroll["status"] == "paid"

        worker = expect(
            client.post(
                "/api/v1/business/domestic/workers",
                json={
                    "store_id": store["id"],
                    "service_type": "maternity",
                    "name": "Worker A",
                    "years_experience": 5,
                    "skills_json": '["newborn care"]',
                    "price_min": 8000,
                    "price_max": 12000,
                    "id_verified": True,
                    "health_verified": True,
                    "training_verified": True,
                },
            ),
            "domestic worker",
        )
        demand = expect(
            client.post(
                "/api/v1/business/domestic/demands",
                json={
                    "customer_id": users["customer"]["id"],
                    "region_id": region["id"],
                    "store_id": store["id"],
                    "service_type": "maternity",
                    "contact_name": "customer",
                    "contact_phone": users["customer"]["phone"],
                    "address": "Flow address",
                    "description": "Maternity care",
                    "detail_json": '{"cycle_days":26}',
                    "budget_min": 9000,
                    "budget_max": 11000,
                    "service_start": "2026-08-01",
                },
            ),
            "domestic demand",
        )
        expect(
            client.post(
                f"/api/v1/business/domestic/demands/{demand['id']}/candidates",
                json={
                    "worker_id": worker["id"],
                    "proposed_by_user_id": users["manager"]["id"],
                },
            ),
            "domestic candidate",
        )
        contract = expect(
            client.post(
                f"/api/v1/business/domestic/demands/{demand['id']}/contract",
                json={
                    "worker_id": worker["id"],
                    "created_by_user_id": users["manager"]["id"],
                    "service_start": "2026-08-01",
                    "service_end": "2026-08-26",
                    "service_fee": 10000,
                    "pass_through_amount": 300,
                    "payment_plan": "deposit_final",
                    "payment_stages": [
                        {"stage_name": "deposit", "amount": 3000},
                        {"stage_name": "final", "amount": 7300},
                    ],
                },
            ),
            "domestic contract",
        )
        stages = expect(
            client.get(
                f"/api/v1/business/domestic/contracts/{contract['id']}/stages"
            ),
            "payment stages",
        )
        for index, stage in enumerate(stages):
            payment = expect(
                client.post(
                    f"/api/v1/business/domestic/stages/{stage['id']}/payment",
                    json={"user_id": payer["id"], "provider": "mock"},
                ),
                f"stage payment {index}",
            )
            expect(
                client.post(
                    "/api/v1/payment/callback",
                    json={
                        "pay_order_id": payment["pay_order_id"],
                        "transaction_id": f"stage-{index}",
                    },
                ),
                f"stage callback {index}",
            )
        expect(
            client.post(
                f"/api/v1/business/domestic/contracts/{contract['id']}/action",
                json={"operator_id": users["manager"]["id"], "action": "start"},
            ),
            "start contract",
        )
        finished_contract = expect(
            client.post(
                f"/api/v1/business/domestic/contracts/{contract['id']}/action",
                json={"operator_id": users["manager"]["id"], "action": "complete"},
            ),
            "complete contract",
        )
        assert finished_contract["status"] == "completed"
        domestic_profit = expect(
            client.get(f"/api/v1/finance/profit/order/{contract['order_id']}"),
            "domestic profits",
        )
        assert abs(domestic_profit["total_distributed"] - 10300) < 0.01

        withdrawal_user = users["manager"]
        withdrawal_wallet = expect(
            client.get(
                f"/api/v1/wallet/balance/{withdrawal_user['id']}",
                headers=hdr(tokens["manager"]),
            ),
            "withdrawal wallet",
        )
        assert withdrawal_wallet["available_balance"] >= 1
        withdrawal = expect(
            client.post(
                f"/api/v1/wallet/withdraw/{withdrawal_user['id']}",
                json={"amount": 1, "remark": "review flow withdrawal"},
                headers=hdr(tokens["manager"]),
            ),
            "partial withdrawal",
        )
        assert withdrawal["amount"] == 1
        after_withdrawal = expect(
            client.get(
                f"/api/v1/wallet/balance/{withdrawal_user['id']}",
                headers=hdr(tokens["manager"]),
            ),
            "wallet after partial withdrawal",
        )
        assert abs(
            after_withdrawal["available_balance"]
            - (withdrawal_wallet["available_balance"] - 1)
        ) < 0.01

    print("auth_roles_and_sms=ok")
    print("review_login_and_partial_withdrawal=ok")
    print("xiamen_service_area_assignment_and_routing=ok")
    print("repair_proxy_claim_payment_warranty=ok")
    print("per_order_and_monthly_payroll=ok")
    print("domestic_matching_installments_profit=ok")


if __name__ == "__main__":
    run()
