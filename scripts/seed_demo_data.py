"""Seed demo accounts and business data through the deployed API.

Usage:
    python scripts/seed_demo_data.py https://x.iddg.cn
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date
from typing import Any

import requests


DEMO_TAG = "[演示]"
FLOW_DEMO_TAG = "[演示全链路]"


@dataclass
class DemoUser:
    key: str
    phone: str
    name: str
    role: str


USERS = [
    DemoUser("admin", "18800000000", "演示管理员", "admin"),
    DemoUser("customer", "18800000001", "演示客户", "customer"),
    DemoUser("repairer", "18800000002", "演示师傅张工", "repairer"),
    DemoUser("second_repairer", "18800000003", "演示二接师傅李工", "repairer"),
    DemoUser("store_manager", "18800000004", "演示门店店长", "admin"),
    DemoUser("city_manager", "18800000005", "演示城市经理", "admin"),
    DemoUser("channel_manager", "18800000006", "演示推广经理", "customer"),
    DemoUser("tech_support", "18800000007", "演示服务保障", "admin"),
    DemoUser("finance", "18800000008", "演示财务", "admin"),
    # 2026-10-07 multi-role:一个账号同时是店长 + 师傅 + 业务。
    # 登录只保证「店长」;师傅 + 业务由 scripts/seed_multi_role_demo.py 补齐,
    # 或者直接在管理后台「用户 → 配置角色」里多选。
    DemoUser("multi_role", "18060936373", "多角色演示", "admin"),
]


class Api:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def request(self, method: str, path: str, **kwargs) -> Any:
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            timeout=30,
            **kwargs,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"{method} {path} failed {response.status_code}: {response.text}"
            )
        if not response.text:
            return None
        return response.json()

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return self.request("POST", path, json=body or {})

    def patch(self, path: str, body: dict[str, Any]) -> Any:
        return self.request("PATCH", path, json=body)


def by_name(items: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((item for item in items if item.get("name") == name), None)


def by_title(items: list[dict[str, Any]], title: str) -> dict[str, Any] | None:
    return next((item for item in items if item.get("title") == title), None)


def first_by(items: list[dict[str, Any]], key: str, value: Any) -> dict[str, Any] | None:
    return next((item for item in items if item.get(key) == value), None)


def login_user(api: Api, user: DemoUser) -> dict[str, Any]:
    result = api.post(
        "/api/v1/auth/wechat-login",
        {"code": f"{user.phone}:{user.name}:{user.role}"},
    )
    return result["user"]


def ensure_region(
    api: Api,
    name: str,
    level: int,
    parent_id: int | None = None,
    manager_id: int | None = None,
) -> dict[str, Any]:
    regions = api.get("/api/v1/regions")
    existing = by_name(regions, name)
    if existing:
        return existing
    body = {
        "name": name,
        "level": level,
        "parent_id": parent_id,
        "manager_id": manager_id,
    }
    return api.post("/api/v1/regions", body)


def ensure_repairer(
    api: Api,
    user_id: int,
    skills: str,
    region_id: int,
    intro: str,
    status: str = "online",
) -> dict[str, Any]:
    repairers = api.get("/api/v1/repairers?limit=100")
    existing = first_by(repairers, "user_id", user_id)
    if not existing:
        existing = api.post(
            "/api/v1/repairers",
            {
                "user_id": user_id,
                "skills": skills,
                "region_id": region_id,
                "intro": intro,
            },
        )
    return api.patch(
        f"/api/v1/repairers/{existing['id']}",
        {
            "skills": skills,
            "status": status,
            "region_id": region_id,
            "intro": intro,
        },
    )


def ensure_store(
    api: Api,
    name: str,
    region_id: int,
    manager_id: int,
    city_manager_id: int,
    default_second_receiver_id: int,
) -> dict[str, Any]:
    stores = api.get("/api/v1/stores")
    existing = by_name(stores, name)
    if not existing:
        existing = api.post(
            "/api/v1/stores",
            {
                "name": name,
                "region_id": region_id,
                "manager_id": manager_id,
                "city_manager_id": city_manager_id,
                "default_second_receiver_id": default_second_receiver_id,
                "remark": f"{DEMO_TAG} H5 演示门店",
            },
        )
    return api.patch(
        f"/api/v1/stores/{existing['id']}",
        {
            "status": "active",
            "enabled": True,
            "manager_id": manager_id,
            "city_manager_id": city_manager_id,
            "default_second_receiver_id": default_second_receiver_id,
        },
    )


def ensure_staff(api: Api, store_id: int, user_id: int, role: str, repairer_id: int | None = None):
    staff = api.get(f"/api/v1/stores/{store_id}/staff")
    if any(item.get("user_id") == user_id and item.get("role") == role for item in staff):
        return
    api.post(
        f"/api/v1/stores/{store_id}/staff",
        {"user_id": user_id, "repairer_id": repairer_id, "role": role},
    )


def ensure_address(api: Api, store_id: int, region_id: int) -> dict[str, Any]:
    addresses = api.get(f"/api/v1/stores/addresses?store_id={store_id}")
    existing = first_by(addresses, "community", "演示花园")
    if existing:
        return existing
    return api.post(
        "/api/v1/stores/addresses",
        {
            "store_id": store_id,
            "region_id": region_id,
            "city": "杭州市",
            "district": "西湖区",
            "street": "文三路",
            "community": "演示花园",
            "detail_hint": "1 幢 101 室，H5 演示地址",
        },
    )


def ensure_package(
    api: Api,
    name: str,
    category: str,
    price: float,
    description: str,
) -> dict[str, Any]:
    packages = api.get("/api/v1/service-packages")
    existing = by_name(packages, name)
    if existing:
        return existing
    return api.post(
        "/api/v1/service-packages",
        {
            "name": name,
            "category": category,
            "service_years": 1,
            "annual_times": 2,
            "device_count": 2,
            "service_month": 3,
            "price": price,
            "description": description,
        },
    )


def ensure_customer_package(
    api: Api,
    package_id: int,
    user_id: int,
    store_id: int,
) -> dict[str, Any] | None:
    mine = api.get(f"/api/v1/service-packages/customer?user_id={user_id}")
    if any(item.get("package_id") == package_id for item in mine):
        return None
    return api.post(
        "/api/v1/service-packages/purchase",
        {
            "package_id": package_id,
            "user_id": user_id,
            "store_id": store_id,
            "address": "杭州市西湖区文三路演示花园 1 幢 101 室",
            "contact_phone": "18800000001",
            "start_date": date.today().isoformat(),
        },
    )


def create_order_if_missing(
    api: Api,
    description: str,
    category: str,
    customer_id: int,
    region_id: int,
    store_id: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    orders = api.get(f"/api/v1/orders?customer_id={customer_id}&limit=100")
    if any(item.get("description") == description for item in orders):
        return None
    service_addresses = api.get("/api/v1/stores/addresses?enabled=true")
    if not service_addresses:
        raise RuntimeError("请先建立标准服务地址后再生成维修演示订单")
    service_address = service_addresses[0]
    body = {
        "customer_id": customer_id,
        "region_id": service_address["region_id"],
        "store_id": service_address["store_id"],
        "address_book_id": service_address["id"],
        "category": category,
        "description": description,
        "address": service_address["full_address"],
        "contact_phone": "18800000001",
        "source": "repair",
    }
    body.update(extra or {})
    return api.post("/api/v1/orders", body)


def ensure_domestic_worker(
    api: Api,
    name: str,
    service_type: str,
    store_id: int,
    years: int,
    skills: list[str],
    price_min: float,
    price_max: float,
) -> dict[str, Any]:
    workers = api.get(f"/api/v1/business/domestic/workers?service_type={service_type}&active=true")
    existing = by_name(workers, name)
    if existing:
        return existing
    return api.post(
        "/api/v1/business/domestic/workers",
        {
            "store_id": store_id,
            "service_type": service_type,
            "name": name,
            "years_experience": years,
            "skills_json": json.dumps(skills, ensure_ascii=False),
            "service_regions_json": json.dumps(["西湖区", "拱墅区"], ensure_ascii=False),
            "availability_text": "近期可预约，具体档期由门店确认",
            "price_min": price_min,
            "price_max": price_max,
            "id_verified": True,
            "health_verified": True,
            "training_verified": True,
            "intro": "资料已由演示门店核验，可预约沟通和面试。",
        },
    )


def ensure_domestic_demand(
    api: Api,
    customer_id: int,
    creator_id: int,
    store_id: int,
    region_id: int,
    service_type: str,
) -> dict[str, Any]:
    demands = api.get(
        f"/api/v1/business/domestic/demands?customer_id={customer_id}&service_type={service_type}"
    )
    marker = f"{DEMO_TAG}{'月嫂' if service_type == 'maternity' else '保姆'}匹配需求"
    existing = next((item for item in demands if item.get("description") == marker), None)
    if existing:
        return existing
    return api.post(
        "/api/v1/business/domestic/demands",
        {
            "customer_id": customer_id,
            "created_by_user_id": creator_id,
            "store_id": store_id,
            "region_id": region_id,
            "service_type": service_type,
            "contact_name": "演示客户",
            "contact_phone": "18800000001",
            "address": "杭州市西湖区文三路演示花园1幢101室",
            "description": marker,
            "detail_json": json.dumps(
                {"cycle_days": 26, "live_in": True}
                if service_type == "maternity"
                else {"service_mode": "白班", "tasks": "做饭、清洁"},
                ensure_ascii=False,
            ),
            "budget_min": 8000 if service_type == "maternity" else 5000,
            "budget_max": 12000 if service_type == "maternity" else 7000,
            "service_start": date.today().isoformat(),
        },
    )


def transition(api: Api, order_id: int, to_status: str, operator_type: str, operator_id: int, remark: str):
    return api.post(
        f"/api/v1/orders/{order_id}/transition",
        {
            "to_status": to_status,
            "operator_type": operator_type,
            "operator_id": operator_id,
            "remark": remark,
        },
    )


def advance_order(
    api: Api,
    order: dict[str, Any] | None,
    repairer_id: int,
    repairer_user_id: int,
    manager_id: int,
    target: str,
    amount: float = 0,
):
    if not order:
        return
    order_id = order["id"]
    if target in {"dispatched", "servicing", "bill_submitted", "wait_payment", "paid_pending_review", "completed"}:
        api.post(f"/api/v1/orders/{order_id}/store-accept?manager_id={manager_id}")
        api.post(f"/api/v1/orders/{order_id}/assign", {"repairer_id": repairer_id})
    if target in {"servicing", "bill_submitted", "wait_payment", "paid_pending_review", "completed"}:
        transition(api, order_id, "repairer_accepted", "repairer", repairer_user_id, "演示师傅接单")
        transition(api, order_id, "servicing", "repairer", repairer_user_id, "演示开始服务")
    if target in {"bill_submitted", "wait_payment", "paid_pending_review", "completed"}:
        api.post(
            f"/api/v1/orders/{order_id}/service-bill",
            {
                "repairer_id": repairer_id,
                "title": "演示服务项目单据",
                "items_json": json.dumps(
                    [{"name": "演示人工费", "quantity": 1, "unit_price": amount, "subtotal": amount}],
                    ensure_ascii=False,
                ),
                "amount": amount,
                "warranty_days": 30,
                "media_json": None,
            },
        )
        if target != "bill_submitted":
            api.post(f"/api/v1/orders/{order_id}/service-bill/confirm")
    if target in {"paid_pending_review", "completed"}:
        payment = api.post(
            "/api/v1/payment/create",
            {
                "order_id": order_id,
                "user_id": order["customer_id"],
                "amount": amount,
                "provider": "mock",
            },
        )
        api.post(
            "/api/v1/payment/callback",
            {
                "pay_order_id": payment["pay_order_id"],
                "transaction_id": f"demo-{order_id}",
                "status": "success",
            },
        )
    if target == "completed":
        api.post(
            f"/api/v1/orders/{order_id}/store-review?manager_id={manager_id}",
            {
                "technician_wage_amount": round(amount * 0.65, 2),
                "remark": "演示门店审核通过",
            },
        )


def ensure_support(api: Api, store_id: int, user_id: int, admin_id: int):
    tickets = api.get("/api/v1/support/tickets")
    title = "演示：空调维修进度咨询"
    ticket = by_title(tickets, title)
    if not ticket:
        ticket = api.post(
            "/api/v1/support/tickets",
            {
                "store_id": store_id,
                "user_id": user_id,
                "category": "order",
                "title": title,
                "content": "师傅已上门，想确认服务单和支付流程。",
            },
        )
    if ticket and ticket.get("status") == "open":
        api.post(
            f"/api/v1/support/tickets/{ticket['id']}/reply",
            {
                "user_id": admin_id,
                "content": "已为您同步订单状态，待确认服务单后即可支付。",
                "close": False,
            },
        )


def seed(base_url: str) -> dict[str, Any]:
    api = Api(base_url)
    accounts = {user.key: login_user(api, user) for user in USERS}

    api.patch(
        f"/api/v1/users/{accounts['channel_manager']['id']}",
        {"is_promotion_manager": True},
    )
    api.patch(
        f"/api/v1/users/{accounts['customer']['id']}",
        {"promotion_manager_id": accounts["channel_manager"]["id"]},
    )

    city = ensure_region(
        api,
        "杭州市演示区",
        2,
        manager_id=accounts["city_manager"]["id"],
    )
    district = ensure_region(
        api,
        "西湖演示片区",
        3,
        parent_id=city["id"],
        manager_id=accounts["store_manager"]["id"],
    )

    repairer = ensure_repairer(
        api,
        accounts["repairer"]["id"],
        "水电维修,家电维修,管道疏通",
        district["id"],
        "5 年上门维修经验，擅长厨卫水电与家电检修。",
    )
    second_repairer = ensure_repairer(
        api,
        accounts["second_repairer"]["id"],
        "二接兜底,空调清洗,门窗维修",
        district["id"],
        "门店默认二接师傅，负责超时兜底和复杂工单。",
        status="busy",
    )

    store = ensure_store(
        api,
        "立即修西湖演示店",
        district["id"],
        accounts["store_manager"]["id"],
        accounts["city_manager"]["id"],
        second_repairer["id"],
    )
    ensure_staff(api, store["id"], accounts["store_manager"]["id"], "manager")
    ensure_staff(api, store["id"], accounts["repairer"]["id"], "technician", repairer["id"])
    ensure_staff(api, store["id"], accounts["second_repairer"]["id"], "second_receiver", second_repairer["id"])
    address = ensure_address(api, store["id"], district["id"])

    xiamen_city = ensure_region(
        api,
        "厦门市演示区域",
        2,
        manager_id=accounts["city_manager"]["id"],
    )
    xiamen_district = ensure_region(
        api,
        "思明演示片区",
        3,
        parent_id=xiamen_city["id"],
        manager_id=accounts["store_manager"]["id"],
    )
    xiamen_store = ensure_store(
        api,
        "立即修厦门演示店",
        xiamen_district["id"],
        accounts["store_manager"]["id"],
        accounts["city_manager"]["id"],
        second_repairer["id"],
    )
    ensure_staff(api, xiamen_store["id"], accounts["store_manager"]["id"], "manager")
    api.post("/api/v1/service-areas/sync-xiamen")
    xiamen_areas = api.get("/api/v1/service-areas?district=思明区&limit=10")
    api.post(
        "/api/v1/service-areas/assignments/bulk",
        {
            "service_area_ids": [item["id"] for item in xiamen_areas["items"]],
            "primary_store_id": xiamen_store["id"],
            "manager_id": accounts["store_manager"]["id"],
            "conflict_mode": "replace",
            "operator_user_id": accounts["admin"]["id"],
            "remark": "厦门地址库演示分配",
        },
    )
    service_area = xiamen_areas["items"][0]
    existing_addresses = api.get(
        f"/api/v1/stores/addresses?service_area_id={service_area['id']}"
    )
    if not any(item.get("address_code") for item in existing_addresses):
        api.post(
            "/api/v1/stores/addresses",
            {
                "service_area_id": service_area["id"],
                "store_id": xiamen_store["id"],
                "estate": "立即修演示小区",
                "building": "1栋",
                "unit": "1单元",
                "room": "101室",
                "business_owner_user_id": accounts["channel_manager"]["id"],
                "created_by_user_id": accounts["admin"]["id"],
                "detail_hint": "平台标准地址演示数据",
            },
        )

    maternity_worker = ensure_domestic_worker(
        api, "演示月嫂王姐", "maternity", store["id"], 8,
        ["新生儿护理", "月子餐", "产妇护理"], 8800, 12800,
    )
    nanny_worker = ensure_domestic_worker(
        api, "演示保姆陈姐", "nanny", store["id"], 6,
        ["家庭做饭", "日常清洁", "老人照护"], 5200, 7200,
    )
    maternity_demand = ensure_domestic_demand(
        api, accounts["customer"]["id"], accounts["customer"]["id"],
        store["id"], district["id"], "maternity",
    )
    nanny_demand = ensure_domestic_demand(
        api, accounts["customer"]["id"], accounts["store_manager"]["id"],
        store["id"], district["id"], "nanny",
    )
    api.post(
        f"/api/v1/business/domestic/demands/{maternity_demand['id']}/candidates",
        {"worker_id": maternity_worker["id"], "proposed_by_user_id": accounts["store_manager"]["id"]},
    )
    api.post(
        f"/api/v1/business/domestic/demands/{nanny_demand['id']}/candidates",
        {"worker_id": nanny_worker["id"], "proposed_by_user_id": accounts["store_manager"]["id"]},
    )

    package_a = ensure_package(
        api,
        "演示空调年度保养卡",
        "appliance",
        299,
        "适合家庭空调年度清洗、巡检和小故障处理。",
    )
    package_b = ensure_package(
        api,
        "演示水电安心包",
        "plumbing",
        199,
        "覆盖漏水、龙头、地漏和简单电路检修。",
    )
    ensure_customer_package(api, package_a["id"], accounts["customer"]["id"], store["id"])
    ensure_customer_package(api, package_b["id"], accounts["customer"]["id"], store["id"])

    order_specs = [
        ("门店待接单", "plumbing", "store_pending", 0),
        ("已派单待师傅接", "electrical", "dispatched", 0),
        ("师傅正在服务", "door_window", "servicing", 0),
        ("服务单待门店确认", "cleaning", "bill_submitted", 128),
        ("服务单待客户支付", "appliance", "wait_payment", 168),
        ("已支付待门店审核", "pipe_dredge", "paid_pending_review", 236),
        ("已完成闭环订单", "furniture_install", "completed", 388),
    ]
    for label, category, target, amount in order_specs:
        order = create_order_if_missing(
            api,
            f"{FLOW_DEMO_TAG}{label}：{category}",
            category,
            accounts["customer"]["id"],
            district["id"],
            store["id"],
        )
        advance_order(
            api,
            order,
            repairer["id"],
            accounts["repairer"]["id"],
            accounts["store_manager"]["id"],
            target,
            amount,
        )

    support_profit_order = create_order_if_missing(
        api,
        f"{DEMO_TAG}服务保障收益订单",
        "appliance",
        accounts["customer"]["id"],
        district["id"],
        store["id"],
    )
    advance_order(
        api,
        support_profit_order,
        repairer["id"],
        accounts["repairer"]["id"],
        accounts["store_manager"]["id"],
        "completed",
        200,
    )

    api.post(
        "/api/v1/business/payroll",
        {
            "month": date.today().strftime("%Y-%m"),
            "store_id": store["id"],
            "manager_id": accounts["store_manager"]["id"],
            "lines": [
                {
                    "employee_user_id": accounts["second_repairer"]["id"],
                    "amount": 5500,
                    "remark": "演示月薪工资单，待店长确认发放",
                }
            ],
        },
    )

    create_order_if_missing(
        api,
        f"{FLOW_DEMO_TAG}电话报修代客订单",
        "plumbing",
        accounts["customer"]["id"],
        district["id"],
        store["id"],
        {
            "created_by_user_id": accounts["store_manager"]["id"],
            "proxy_creator_id": accounts["store_manager"]["id"],
            "is_proxy_order": True,
            "proxy_reason": "phone_request",
            "customer_name_snapshot": "演示客户",
            "customer_phone_snapshot": "18800000001",
            "customer_address_snapshot": "杭州市西湖区文三路演示花园 1 幢 101 室",
        },
    )

    ensure_support(
        api,
        store["id"],
        accounts["customer"]["id"],
        accounts["admin"]["id"],
    )

    for account in accounts.values():
        api.get(f"/api/v1/wallet/balance/{account['id']}")

    return {
        "accounts": accounts,
        "region": district,
        "store": store,
        "xiamen_store": xiamen_store,
        "address": address,
        "repairer": repairer,
        "second_repairer": second_repairer,
        "packages": [package_a, package_b],
        "domestic_workers": [maternity_worker, nanny_worker],
        "domestic_demands": [maternity_demand, nanny_demand],
    }


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "https://x.iddg.cn"
    result = seed(base_url)
    summary = {
        "base_url": base_url,
        "accounts": {
            key: {
                "id": user["id"],
                "phone": user["phone"],
                "name": user["name"],
                "role": user["role"],
            }
            for key, user in result["accounts"].items()
        },
        "store_id": result["store"]["id"],
        "xiamen_store_id": result["xiamen_store"]["id"],
        "repairer_id": result["repairer"]["id"],
        "second_repairer_id": result["second_repairer"]["id"],
        "package_ids": [pkg["id"] for pkg in result["packages"]],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
