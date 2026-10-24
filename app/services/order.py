"""Order workflow services."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.business import WageRecord, WarrantyCertificate
from ..models.order import Order, OrderSource, OrderStatus, validate_transition
from ..models.order_log import OperatorType, OrderLog
from ..models.repairer import Repairer
from ..models.service_area import ServiceArea, ServiceAreaAssignment
from ..models.store import Store, StoreStaff, StoreStaffRole, StoreStatus
from ..models.user import User
from ..schemas.order import OrderCreate, OrderUpdate
from .store import find_active_store_by_region, find_address
from .address_format import clean, door_number, full_address as format_address
from .service_area import match_service_area, resolve_open_area


def _canonical_status(status: OrderStatus) -> OrderStatus:
    if status == OrderStatus.PENDING:
        return OrderStatus.CREATED
    if status == OrderStatus.ASSIGNED:
        return OrderStatus.DISPATCHED
    if status == OrderStatus.ACCEPTED:
        return OrderStatus.REPAIRER_ACCEPTED
    if status == OrderStatus.IN_PROGRESS:
        return OrderStatus.SERVICING
    return status


def _coerce_order_status(status: str) -> OrderStatus:
    try:
        return OrderStatus(status)
    except ValueError:
        try:
            return OrderStatus[status.upper()]
        except KeyError as exc:
            raise ValueError(f"Unsupported order status: {status}") from exc


async def write_log(
    db: AsyncSession,
    order: Order,
    from_status: str,
    to_status: str,
    operator_type: str,
    operator_id: int | None = None,
    remark: str | None = None,
) -> OrderLog:
    log = OrderLog(
        order_id=order.id,
        from_status=from_status,
        to_status=to_status,
        operator_type=operator_type,
        operator_id=operator_id,
        remark=remark,
    )
    db.add(log)
    return log


async def transition_status(
    db: AsyncSession,
    order: Order,
    to_status: OrderStatus,
    operator_type: str = "system",
    operator_id: int | None = None,
    remark: str | None = None,
) -> Order:
    from_status = order.status
    from_canonical = _canonical_status(from_status)
    to_canonical = _canonical_status(to_status)

    if not validate_transition(from_status, to_status) and not validate_transition(
        from_canonical, to_canonical
    ):
        raise ValueError(f"Illegal status transition: {from_status.value} -> {to_status.value}")

    await write_log(
        db,
        order,
        from_status=from_status.value,
        to_status=to_status.value,
        operator_type=operator_type,
        operator_id=operator_id,
        remark=remark,
    )

    order.status = to_status
    now = datetime.now(timezone.utc)
    if to_status in (OrderStatus.DISPATCHED, OrderStatus.ASSIGNED):
        order.assigned_at = now
    if to_status in (OrderStatus.REPAIRER_ACCEPTED, OrderStatus.ACCEPTED):
        order.repairer_id = order.repairer_id or order.assigned_repairer_id
    if to_status == OrderStatus.PAID:
        order.paid_at = now
    if to_status == OrderStatus.STORE_REVIEWED:
        order.store_reviewed_at = now
    if to_status == OrderStatus.COMPLETED and order.completed_at is None:
        order.completed_at = now

    await db.commit()
    await db.refresh(order)

    if to_status == OrderStatus.PAID_PENDING_REVIEW and order.price > 0:
        from .profit import calculate_and_save

        await calculate_and_save(db, order)

    return order


async def create_order(db: AsyncSession, data: OrderCreate) -> Order:
    payload = data.model_dump()
    payload.pop("respect_service_area", None)
    controlled_sources = {
        OrderSource.REPAIR,
        OrderSource.PACKAGE,
        OrderSource.AFTER_SALES,
    }
    service_address = None
    if data.source in controlled_sources and not data.service_area_id:
        if not data.address_book_id:
            raise ValueError("请选择地址库中的标准上门地址，联系电话不能代替地址归属")
        service_address = await find_address(db, data.address_book_id)
        if not service_address or not service_address.enabled or not service_address.full_address:
            raise ValueError("所选标准地址无效或尚未开通服务")

    customer = await db.get(User, data.customer_id)
    if customer:
        payload["created_by_user_id"] = data.created_by_user_id or data.customer_id
        payload["customer_name_snapshot"] = data.customer_name_snapshot or customer.name
        payload["customer_phone_snapshot"] = (
            data.customer_phone_snapshot or data.contact_phone or customer.phone
        )
        payload["customer_address_snapshot"] = data.customer_address_snapshot or data.address
        payload["referrer_user_id"] = customer.referrer_user_id
        payload["channel_manager_id_snapshot"] = data.channel_manager_id_snapshot
    if data.is_proxy_order:
        payload["claim_status"] = "unclaimed"
        payload["proxy_creator_id"] = data.proxy_creator_id or data.created_by_user_id
        payload["risk_review_required"] = bool(
            payload["proxy_creator_id"] and payload["proxy_creator_id"] == data.customer_id
        )
    matched_area = None
    area_assignment = None
    store = None
    if data.service_area_id:
        matched_area, area_assignment, store = await resolve_open_area(db, data.service_area_id)
        door = door_number(data.door_number, data.building, data.unit, data.room)
        full_address = format_address(matched_area.city, matched_area.district, data.estate, door)
        payload.update(estate=clean(data.estate), door_number=door,
                       building=data.building, unit=data.unit, room=data.room)
        payload.update(address=full_address, customer_address_snapshot=full_address,
            region_id=store.region_id, store_id=store.id, address_book_id=None,
            address_code_snapshot=matched_area.code, address_owner_user_id=store.manager_id,
            channel_manager_id_snapshot=store.manager_id)
    elif service_address:
        matched_area = (
            await db.get(ServiceArea, service_address.service_area_id)
            if service_address.service_area_id else None
        )
        if not matched_area or not matched_area.active:
            raise ValueError("标准地址对应的服务区域已停用")
        area_assignment = (
            await db.execute(
                select(ServiceAreaAssignment).where(
                    ServiceAreaAssignment.service_area_id == matched_area.id
                )
            )
        ).scalar_one_or_none()
        matched_area, area_assignment, store = await resolve_open_area(db, service_address.service_area_id)
        door = door_number(service_address.door_number, service_address.building, service_address.unit, service_address.room)
        normalized_address = format_address(matched_area.city, matched_area.district, service_address.estate, door)
        payload.update({
            "address": normalized_address,
            "customer_address_snapshot": normalized_address,
            "estate": service_address.estate, "door_number": door,
            "region_id": store.region_id,
            "store_id": store.id,
            "address_code_snapshot": service_address.address_code,
            "address_owner_user_id": service_address.business_owner_user_id,
            "channel_manager_id_snapshot": (
                service_address.business_owner_user_id
                or (area_assignment.manager_id if area_assignment else None)
            ),
        })
    else:
        matched_area, area_assignment, matched_store = await match_service_area(db, data.address)
        store = matched_store if data.respect_service_area else None
        if store is None and data.store_id:
            store = await db.get(Store, data.store_id)
        if store is None:
            store = await find_active_store_by_region(db, data.region_id)

    if matched_area:
        payload["service_area_id"] = matched_area.id
        payload["service_area_district_snapshot"] = matched_area.district
        payload["service_area_street_snapshot"] = matched_area.street
        payload["service_area_name_snapshot"] = matched_area.name
    if area_assignment:
        payload["service_area_assignment_id"] = area_assignment.id
        payload["service_area_manager_id"] = store.manager_id if store else area_assignment.manager_id

    if store:
        payload["store_id"] = store.id
        status = OrderStatus.STORE_PENDING
        payload["assigned_at"] = datetime.now(timezone.utc)
    else:
        status = OrderStatus.CREATED

    order = Order(**payload, status=status)
    db.add(order)
    await db.commit()
    await db.refresh(order)

    await write_log(
        db,
        order,
        from_status="",
        to_status=order.status.value,
        operator_type=OperatorType.CUSTOMER,
        operator_id=data.customer_id,
        remark="order created",
    )
    await db.commit()
    await db.refresh(order)
    return order


async def get_order(db: AsyncSession, order_id: int) -> Order | None:
    return await db.get(Order, order_id)


async def list_orders(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    customer_id: int | None = None,
    repairer_id: int | None = None,
    assigned_repairer_id: int | None = None,
    status: str | None = None,
    region_id: int | None = None,
    store_id: int | None = None,
    is_proxy_order: bool | None = None,
) -> list[Order]:
    stmt = select(Order)
    if customer_id:
        stmt = stmt.where(Order.customer_id == customer_id)
    if repairer_id:
        stmt = stmt.where(Order.repairer_id == repairer_id)
    if assigned_repairer_id:
        stmt = stmt.where(Order.assigned_repairer_id == assigned_repairer_id)
    if status:
        stmt = stmt.where(Order.status == _coerce_order_status(status))
    if region_id:
        stmt = stmt.where(Order.region_id == region_id)
    if store_id:
        stmt = stmt.where(Order.store_id == store_id)
    if is_proxy_order is not None:
        stmt = stmt.where(Order.is_proxy_order == is_proxy_order)
    stmt = stmt.order_by(Order.id.desc()).offset(skip).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def update_order(db: AsyncSession, order: Order, data: OrderUpdate) -> Order:
    if data.status is not None:
        return await transition_status(db, order, data.status, operator_type="admin")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(order, key, value)
    await db.commit()
    await db.refresh(order)
    return order


async def manual_assign(db: AsyncSession, order: Order, repairer_id: int) -> Order:
    repairer = await db.get(Repairer, repairer_id)
    if not repairer:
        raise ValueError(f"Repairer #{repairer_id} not found")

    order.assigned_repairer_id = repairer_id
    target = OrderStatus.DISPATCHED if order.status != OrderStatus.CREATED else OrderStatus.ASSIGNED
    return await transition_status(
        db,
        order,
        target,
        operator_type=OperatorType.ADMIN,
        remark=f"assigned to repairer #{repairer_id}",
    )


async def store_accept(db: AsyncSession, order: Order, manager_id: int | None = None) -> Order:
    return await transition_status(
        db,
        order,
        OrderStatus.STORE_ACCEPTED,
        operator_type=OperatorType.ADMIN,
        operator_id=manager_id,
        remark="store accepted",
    )


async def store_self_service(
    db: AsyncSession,
    order: Order,
    manager_id: int,
    skills: str = "门店综合服务",
) -> Order:
    if not order.store_id:
        raise ValueError("Order is not assigned to a store")
    store = await db.get(Store, order.store_id)
    if not store or store.manager_id != manager_id:
        raise ValueError("Only the store manager can choose self-service")
    repairer = (
        await db.execute(select(Repairer).where(Repairer.user_id == manager_id))
    ).scalar_one_or_none()
    if not repairer:
        repairer = Repairer(
            user_id=manager_id,
            skills=skills,
            status="online",
            region_id=store.region_id,
            id_verified=True,
            intro="门店店长兼任服务师傅",
        )
        db.add(repairer)
        await db.flush()
    staff = (
        await db.execute(
            select(StoreStaff).where(
                StoreStaff.store_id == store.id,
                StoreStaff.user_id == manager_id,
                StoreStaff.role == StoreStaffRole.MANAGER,
            )
        )
    ).scalar_one_or_none()
    if not staff:
        db.add(StoreStaff(
            store_id=store.id,
            user_id=manager_id,
            repairer_id=repairer.id,
            role=StoreStaffRole.MANAGER,
        ))
    else:
        staff.repairer_id = repairer.id
    await db.commit()
    if order.status == OrderStatus.STORE_PENDING:
        await store_accept(db, order, manager_id)
        await db.refresh(order)
    order.assigned_repairer_id = repairer.id
    return await transition_status(
        db,
        order,
        OrderStatus.DISPATCHED,
        operator_type=OperatorType.ADMIN,
        operator_id=manager_id,
        remark="store manager selected self-service",
    )


async def auto_dispatch(db: AsyncSession, order: Order) -> Order:
    if order.status not in (
        OrderStatus.STORE_PENDING,
        OrderStatus.STORE_ACCEPTED,
        OrderStatus.CREATED,
        OrderStatus.PENDING,
    ):
        raise ValueError("Only pending orders can be dispatched")

    if not order.store_id:
        store = await find_active_store_by_region(db, order.region_id)
    else:
        store = await db.get(Store, order.store_id)

    if not store or not store.default_second_receiver_id:
        raise ValueError("Store default second receiver is not configured")

    order.store_id = store.id
    order.assigned_repairer_id = store.default_second_receiver_id
    return await transition_status(
        db,
        order,
        OrderStatus.DISPATCHED,
        operator_type=OperatorType.SYSTEM,
        remark=f"default second receiver #{store.default_second_receiver_id}",
    )


async def timeout_reassign(db: AsyncSession, order: Order) -> Order | None:
    if order.status != OrderStatus.STORE_PENDING:
        return None

    start = order.assigned_at or order.created_at
    if start is None:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    if elapsed < 600:
        return None
    return await auto_dispatch(db, order)


async def store_review_complete(
    db: AsyncSession,
    order: Order,
    technician_wage_amount: float,
    manager_id: int | None = None,
    remark: str | None = None,
    wage_mode: str = "per_order",
) -> Order:
    if order.status not in (
        OrderStatus.PAID_PENDING_REVIEW,
        OrderStatus.PAID,
        OrderStatus.STORE_REVIEWED,
    ):
        raise ValueError("Only paid orders can be store-reviewed")

    if wage_mode not in ("per_order", "monthly"):
        raise ValueError("Unsupported wage mode")
    if wage_mode == "monthly" and technician_wage_amount != 0:
        raise ValueError("Monthly employees cannot receive a per-order wage")
    order.technician_wage_amount = technician_wage_amount
    order.wage_mode = wage_mode

    if order.status == OrderStatus.PAID:
        await transition_status(
            db,
            order,
            OrderStatus.PAID_PENDING_REVIEW,
            operator_type=OperatorType.SYSTEM,
            remark="payment completed, waiting for store review",
        )
        await db.refresh(order)

    if order.status != OrderStatus.STORE_REVIEWED:
        await transition_status(
            db,
            order,
            OrderStatus.STORE_REVIEWED,
            operator_type=OperatorType.ADMIN,
            operator_id=manager_id,
            remark=remark or "store review completed",
        )
        await db.refresh(order)

    repairer_id = order.repairer_id or order.assigned_repairer_id
    if not repairer_id:
        raise ValueError("Order has no repairer for wage review")
    repairer = await db.get(Repairer, repairer_id)
    if not repairer:
        raise ValueError("Repairer not found")
    existing_wage = (
        await db.execute(select(WageRecord).where(WageRecord.order_id == order.id))
    ).scalar_one_or_none()
    if not existing_wage:
        db.add(WageRecord(
            order_id=order.id,
            store_id=order.store_id,
            repairer_id=repairer_id,
            employee_user_id=repairer.user_id,
            wage_mode=wage_mode,
            amount=technician_wage_amount,
            status="approved" if wage_mode == "monthly" else "pending_settlement",
            reviewed_by_user_id=manager_id,
            remark=remark,
        ))
        await db.commit()

    from .profit import apply_per_order_wage, calculate_and_save
    from .service_bill import get_latest_bill
    from .wallet import settle_profit_shares

    profits = (
        await apply_per_order_wage(db, order, repairer.user_id, technician_wage_amount)
        if wage_mode == "per_order"
        else await calculate_and_save(db, order)
    )
    await settle_profit_shares(db, profits)
    order.settlement_status = "settled"
    wage_record = (
        await db.execute(select(WageRecord).where(WageRecord.order_id == order.id))
    ).scalar_one_or_none()
    if wage_record and wage_mode == "per_order":
        wage_record.status = "paid"
        wage_record.paid_at = datetime.now(timezone.utc)
        await db.commit()

    bill = await get_latest_bill(db, order.id)
    if bill:
        warranty = (
            await db.execute(
                select(WarrantyCertificate).where(WarrantyCertificate.order_id == order.id)
            )
        ).scalar_one_or_none()
        if not warranty:
            starts_at = order.paid_at or datetime.now(timezone.utc)
            db.add(WarrantyCertificate(
                certificate_no=f"XJBX{order.id:010d}",
                order_id=order.id,
                customer_id=order.customer_id,
                service_bill_id=bill.id,
                store_id=order.store_id,
                repairer_id=repairer_id,
                items_json=bill.items_json,
                amount=bill.amount,
                warranty_days=bill.warranty_days,
                starts_at=starts_at,
                expires_at=starts_at + timedelta(days=bill.warranty_days),
            ))
            await db.commit()

    completed = await transition_status(
        db,
        order,
        OrderStatus.COMPLETED,
        operator_type=OperatorType.SYSTEM,
        remark="order archived after store review",
    )
    return completed


async def rate_order(
    db: AsyncSession, order: Order, rating: int, remark: str | None = None
) -> Order:
    order.rating = rating
    order.rating_remark = remark
    await db.commit()
    await db.refresh(order)
    return order


async def get_order_logs(db: AsyncSession, order_id: int) -> list[OrderLog]:
    result = await db.execute(
        select(OrderLog).where(OrderLog.order_id == order_id).order_by(OrderLog.created_at.asc())
    )
    return list(result.scalars().all())
