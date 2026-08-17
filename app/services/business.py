"""Business workflows shared by repair, proxy-order, and domestic services."""

import hashlib
import secrets
import calendar
from datetime import date
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.business import (
    CustomerAddress,
    DomesticCandidate,
    DomesticContract,
    DomesticDemand,
    DomesticPaymentStage,
    DomesticWorker,
    OrderAccessToken,
    WageRecord,
    WarrantyCertificate,
)
from ..models.order import Order, OrderCategory, OrderSource, OrderStatus
from ..models.ledger import LedgerType
from ..models.settlement import (
    SettlementItem,
    SettlementItemType,
    SettlementPeriod,
    SettlementStatus,
)
from ..models.store import Store, StoreAddress
from ..models.user import User
from ..schemas.business import (
    AddressCreate,
    AddressUpdate,
    CandidateCreate,
    CandidateUpdate,
    ContractCreate,
    DomesticDemandCreate,
    DomesticDemandUpdate,
    DomesticWorkerCreate,
    DomesticWorkerUpdate,
    PayrollCreate,
)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def list_addresses(db: AsyncSession, user_id: int) -> list[CustomerAddress]:
    rows = await db.execute(
        select(CustomerAddress)
        .where(CustomerAddress.user_id == user_id, CustomerAddress.enabled.is_(True))
        .order_by(CustomerAddress.is_default.desc(), CustomerAddress.id.desc())
    )
    return list(rows.scalars().all())


async def create_address(db: AsyncSession, data: AddressCreate) -> CustomerAddress:
    service_address = await db.get(StoreAddress, data.service_address_id)
    if not service_address or not service_address.enabled or not service_address.full_address:
        raise ValueError("请选择地址库中已开通的标准服务地址")
    existing = (
        await db.execute(
            select(CustomerAddress).where(
                CustomerAddress.user_id == data.user_id,
                CustomerAddress.service_address_id == data.service_address_id,
                CustomerAddress.enabled.is_(True),
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise ValueError("该服务地址已经保存在地址簿中")
    if data.is_default:
        await db.execute(
            update(CustomerAddress)
            .where(CustomerAddress.user_id == data.user_id)
            .values(is_default=False)
        )
    address = CustomerAddress(
        **data.model_dump(),
        region_id=service_address.region_id,
        address=service_address.full_address,
    )
    db.add(address)
    await db.commit()
    await db.refresh(address)
    return address


async def update_address(
    db: AsyncSession, address: CustomerAddress, data: AddressUpdate
) -> CustomerAddress:
    values = data.model_dump(exclude_unset=True)
    if values.get("is_default"):
        await db.execute(
            update(CustomerAddress)
            .where(CustomerAddress.user_id == address.user_id)
            .values(is_default=False)
        )
    for key, value in values.items():
        setattr(address, key, value)
    await db.commit()
    await db.refresh(address)
    return address


async def create_access_token(
    db: AsyncSession,
    order: Order,
    purpose: str,
    created_by_user_id: int | None,
) -> tuple[str, OrderAccessToken]:
    if purpose not in ("claim", "payment"):
        raise ValueError("Unsupported access purpose")
    if purpose == "claim" and not order.is_proxy_order:
        raise ValueError("Only proxy orders can generate a claim code")
    if purpose == "payment" and order.status != OrderStatus.WAIT_PAYMENT:
        raise ValueError("Payment code is only available for unpaid orders")

    now = datetime.now(timezone.utc)
    old_rows = await db.execute(
        select(OrderAccessToken).where(
            OrderAccessToken.order_id == order.id,
            OrderAccessToken.purpose == purpose,
            OrderAccessToken.revoked_at.is_(None),
        )
    )
    for old in old_rows.scalars().all():
        old.revoked_at = now

    token = secrets.token_urlsafe(24)
    item = OrderAccessToken(
        order_id=order.id,
        purpose=purpose,
        token_hash=_token_hash(token),
        created_by_user_id=created_by_user_id,
        expires_at=now + (timedelta(hours=24) if purpose == "claim" else timedelta(hours=2)),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return token, item


async def resolve_access_token(
    db: AsyncSession, token: str, purpose: str | None = None
) -> tuple[OrderAccessToken, Order]:
    item = (
        await db.execute(
            select(OrderAccessToken).where(OrderAccessToken.token_hash == _token_hash(token))
        )
    ).scalar_one_or_none()
    if not item or item.revoked_at:
        raise ValueError("Access code is invalid")
    expires_at = item.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise ValueError("Access code has expired")
    if purpose and item.purpose != purpose:
        raise ValueError("Access code purpose does not match")
    order = await db.get(Order, item.order_id)
    if not order:
        raise ValueError("Order not found")
    if item.purpose == "payment" and order.status != OrderStatus.WAIT_PAYMENT:
        raise ValueError("This order no longer needs payment")
    return item, order


async def claim_order(
    db: AsyncSession, token: str, user_id: int, verification_phone: str | None
) -> tuple[Order, str]:
    item, order = await resolve_access_token(db, token, "claim")
    user = await db.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    expected_phone = order.customer_phone_snapshot or order.contact_phone
    verified_phone = verification_phone or user.phone
    if not expected_phone or verified_phone != expected_phone:
        return order, "pay_only"
    order.customer_id = user.id
    order.claimed_by_user_id = user.id
    order.claim_status = "claimed"
    order.claimed_at = datetime.now(timezone.utc)
    item.used_at = order.claimed_at
    item.revoked_at = order.claimed_at
    await db.commit()
    await db.refresh(order)
    return order, "claimed"


async def list_warranties(
    db: AsyncSession,
    customer_id: int | None = None,
    phone: str | None = None,
    include_expired: bool = False,
) -> list[WarrantyCertificate]:
    now = datetime.now(timezone.utc)
    expired = await db.execute(
        update(WarrantyCertificate)
        .where(
            WarrantyCertificate.status == "active",
            WarrantyCertificate.expires_at <= now,
        )
        .values(status="expired")
    )
    if expired.rowcount:
        await db.commit()

    stmt = select(WarrantyCertificate)
    if customer_id:
        stmt = stmt.where(WarrantyCertificate.customer_id == customer_id)
    elif phone:
        stmt = stmt.join(User, User.id == WarrantyCertificate.customer_id).where(User.phone == phone)
    if not include_expired:
        stmt = stmt.where(
            WarrantyCertificate.status == "active",
            WarrantyCertificate.expires_at > now,
        )
    rows = await db.execute(stmt.order_by(WarrantyCertificate.id.desc()))
    return list(rows.scalars().all())


async def list_wages(
    db: AsyncSession,
    store_id: int | None = None,
    employee_user_id: int | None = None,
    wage_mode: str | None = None,
) -> list[WageRecord]:
    stmt = select(WageRecord)
    if store_id:
        stmt = stmt.where(WageRecord.store_id == store_id)
    if employee_user_id:
        stmt = stmt.where(WageRecord.employee_user_id == employee_user_id)
    if wage_mode:
        stmt = stmt.where(WageRecord.wage_mode == wage_mode)
    rows = await db.execute(stmt.order_by(WageRecord.id.desc()))
    return list(rows.scalars().all())


async def create_payroll(db: AsyncSession, data: PayrollCreate) -> SettlementPeriod:
    year, month = (int(part) for part in data.month.split("-"))
    period = (
        await db.execute(select(SettlementPeriod).where(SettlementPeriod.month == data.month))
    ).scalar_one_or_none()
    if not period:
        period = SettlementPeriod(
            month=data.month,
            period_start=date(year, month, 1),
            period_end=date(year, month, calendar.monthrange(year, month)[1]),
            status=SettlementStatus.STORE_REVIEW,
        )
        db.add(period)
        await db.flush()
    for line in data.lines:
        existing = (
            await db.execute(
                select(SettlementItem).where(
                    SettlementItem.period_id == period.id,
                    SettlementItem.store_id == data.store_id,
                    SettlementItem.user_id == line.employee_user_id,
                    SettlementItem.item_type == SettlementItemType.TECHNICIAN_WAGE,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.amount = line.amount
            existing.remark = line.remark
            existing.status = SettlementStatus.STORE_REVIEW
        else:
            db.add(SettlementItem(
                period_id=period.id,
                user_id=line.employee_user_id,
                store_id=data.store_id,
                item_type=SettlementItemType.TECHNICIAN_WAGE,
                amount=line.amount,
                status=SettlementStatus.STORE_REVIEW,
                remark=line.remark,
            ))
    await db.commit()
    await db.refresh(period)
    return period


async def pay_payroll(
    db: AsyncSession, period_id: int, store_id: int, manager_id: int
) -> SettlementPeriod:
    period = await db.get(SettlementPeriod, period_id)
    store = await db.get(Store, store_id)
    if not period or not store:
        raise ValueError("Payroll period or store not found")
    if store.manager_id != manager_id:
        raise ValueError("Only the store manager can pay this payroll")
    items = list((await db.execute(
        select(SettlementItem).where(
            SettlementItem.period_id == period_id,
            SettlementItem.store_id == store_id,
            SettlementItem.item_type == SettlementItemType.TECHNICIAN_WAGE,
            SettlementItem.status != SettlementStatus.PAID,
        )
    )).scalars().all())
    from . import safety
    for item in items:
        if not item.user_id:
            continue
        await safety.safe_transfer(
            db,
            from_user_id=manager_id,
            to_user_id=item.user_id,
            amount=item.amount,
            debit_type=LedgerType.MONTHLY_WAGE_PAYMENT,
            credit_type=LedgerType.TECHNICIAN_WAGE,
            ref_type="settlement_item",
            ref_id=item.id,
            remark=f"{period.month}月薪: {item.remark or ''}",
        )
        item.status = SettlementStatus.PAID
        item.paid_at = datetime.now(timezone.utc)
        await db.commit()
    remaining = (
        await db.execute(
            select(SettlementItem.id).where(
                SettlementItem.period_id == period_id,
                SettlementItem.status != SettlementStatus.PAID,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if not remaining:
        period.status = SettlementStatus.PAID
        await db.commit()
    await db.refresh(period)
    return period


async def list_workers(
    db: AsyncSession, service_type: str | None, store_id: int | None, active: bool
) -> list[DomesticWorker]:
    stmt = select(DomesticWorker).where(DomesticWorker.active.is_(active))
    if service_type:
        stmt = stmt.where(DomesticWorker.service_type == service_type)
    if store_id:
        stmt = stmt.where(DomesticWorker.store_id == store_id)
    rows = await db.execute(stmt.order_by(DomesticWorker.rating.desc(), DomesticWorker.id.desc()))
    return list(rows.scalars().all())


async def create_worker(db: AsyncSession, data: DomesticWorkerCreate) -> DomesticWorker:
    worker = DomesticWorker(**data.model_dump())
    db.add(worker)
    await db.commit()
    await db.refresh(worker)
    return worker


async def update_worker(
    db: AsyncSession, worker: DomesticWorker, data: DomesticWorkerUpdate
) -> DomesticWorker:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(worker, key, value)
    await db.commit()
    await db.refresh(worker)
    return worker


async def create_demand(db: AsyncSession, data: DomesticDemandCreate) -> DomesticDemand:
    customer = await db.get(User, data.customer_id)
    if not customer:
        raise ValueError("Customer not found")
    payload = data.model_dump()
    payload["created_by_user_id"] = data.created_by_user_id or data.customer_id
    payload["channel_manager_id_snapshot"] = customer.promotion_manager_id
    if data.is_proxy_order:
        payload["proxy_creator_id"] = data.proxy_creator_id or payload["created_by_user_id"]
    demand = DomesticDemand(**payload)
    db.add(demand)
    await db.commit()
    await db.refresh(demand)
    return demand


async def list_demands(
    db: AsyncSession,
    customer_id: int | None,
    store_id: int | None,
    service_type: str | None,
    status: str | None,
) -> list[DomesticDemand]:
    stmt = select(DomesticDemand)
    if customer_id:
        stmt = stmt.where(DomesticDemand.customer_id == customer_id)
    if store_id:
        stmt = stmt.where(DomesticDemand.store_id == store_id)
    if service_type:
        stmt = stmt.where(DomesticDemand.service_type == service_type)
    if status:
        stmt = stmt.where(DomesticDemand.status == status)
    rows = await db.execute(stmt.order_by(DomesticDemand.id.desc()))
    return list(rows.scalars().all())


async def update_demand(
    db: AsyncSession, demand: DomesticDemand, data: DomesticDemandUpdate
) -> DomesticDemand:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(demand, key, value)
    await db.commit()
    await db.refresh(demand)
    return demand


async def add_candidate(
    db: AsyncSession, demand: DomesticDemand, data: CandidateCreate
) -> DomesticCandidate:
    worker = await db.get(DomesticWorker, data.worker_id)
    if not worker or worker.service_type != demand.service_type:
        raise ValueError("Worker does not match the demand type")
    existing = (
        await db.execute(
            select(DomesticCandidate).where(
                DomesticCandidate.demand_id == demand.id,
                DomesticCandidate.worker_id == data.worker_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    candidate = DomesticCandidate(demand_id=demand.id, **data.model_dump())
    db.add(candidate)
    demand.status = "matching"
    await db.commit()
    await db.refresh(candidate)
    return candidate


async def update_candidate(
    db: AsyncSession, candidate: DomesticCandidate, data: CandidateUpdate
) -> DomesticCandidate:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(candidate, key, value)
    await db.commit()
    await db.refresh(candidate)
    return candidate


async def create_contract(
    db: AsyncSession, demand: DomesticDemand, data: ContractCreate
) -> DomesticContract:
    existing = (
        await db.execute(select(DomesticContract).where(DomesticContract.demand_id == demand.id))
    ).scalar_one_or_none()
    if existing:
        return existing
    worker = await db.get(DomesticWorker, data.worker_id)
    if not worker or worker.service_type != demand.service_type:
        raise ValueError("Selected worker does not match the demand")
    total = round(data.service_fee + data.pass_through_amount, 2)
    stages = data.payment_stages
    if stages and abs(sum(item.amount for item in stages) - total) > 0.01:
        raise ValueError("Payment stages must add up to the contract total")
    if not stages:
        from ..schemas.business import PaymentStageInput
        stages = [PaymentStageInput(stage_name="全款", amount=total, due_date=data.service_start)]

    order = Order(
        customer_id=demand.customer_id,
        created_by_user_id=data.created_by_user_id,
        proxy_creator_id=demand.proxy_creator_id,
        referrer_user_id=demand.channel_manager_id_snapshot,
        channel_manager_id_snapshot=demand.channel_manager_id_snapshot,
        is_proxy_order=demand.is_proxy_order,
        proxy_reason="domestic_assistance" if demand.is_proxy_order else None,
        claim_status="unclaimed" if demand.is_proxy_order else "not_required",
        customer_name_snapshot=demand.contact_name,
        customer_phone_snapshot=demand.contact_phone,
        customer_address_snapshot=demand.address,
        store_id=demand.store_id,
        source=OrderSource.MATERNITY if demand.service_type == "maternity" else OrderSource.NANNY,
        region_id=demand.region_id,
        category=OrderCategory.OTHER,
        description=demand.description or ("月嫂服务" if demand.service_type == "maternity" else "保姆服务"),
        media_json=demand.media_json,
        address=demand.address,
        contact_phone=demand.contact_phone,
        price=total,
        commissionable_amount=data.service_fee,
        status=OrderStatus.WAIT_PAYMENT,
    )
    db.add(order)
    await db.flush()
    contract = DomesticContract(
        demand_id=demand.id,
        order_id=order.id,
        customer_id=demand.customer_id,
        worker_id=worker.id,
        store_id=demand.store_id,
        created_by_user_id=data.created_by_user_id,
        service_start=data.service_start,
        service_end=data.service_end,
        service_fee=data.service_fee,
        pass_through_amount=data.pass_through_amount,
        payment_plan=data.payment_plan,
        agreement_json=data.agreement_json,
    )
    db.add(contract)
    await db.flush()
    for stage in stages:
        db.add(DomesticPaymentStage(contract_id=contract.id, **stage.model_dump()))
    demand.selected_worker_id = worker.id
    demand.status = "contracted"
    await db.commit()
    await db.refresh(contract)
    return contract


async def contract_action(
    db: AsyncSession, contract: DomesticContract, action: str, remark: str | None
) -> DomesticContract:
    if action == "start":
        if contract.status not in ("paid", "in_service"):
            raise ValueError("The contract must receive payment before service starts")
        contract.status = "in_service"
    elif action == "complete":
        order = await db.get(Order, contract.order_id)
        if not order or order.paid_amount + 0.01 < order.price:
            raise ValueError("The contract is not fully paid")
        from .profit import calculate_and_save
        from .wallet import settle_profit_shares
        profits = await calculate_and_save(db, order)
        await settle_profit_shares(db, profits)
        order.settlement_status = "settled"
        order.status = OrderStatus.COMPLETED
        order.completed_at = datetime.now(timezone.utc)
        contract.status = "completed"
    elif action == "terminate":
        contract.status = "terminated"
        contract.terminated_at = datetime.now(timezone.utc)
    elif action == "complaint":
        contract.status = "complaint"
    await db.commit()
    await db.refresh(contract)
    return contract
