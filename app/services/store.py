"""Store management services."""

import hashlib
import re
import unicodedata

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.service_area import ServiceArea, ServiceAreaAssignment
from ..models.store import (
    AreaOpenRequest,
    Store,
    StoreAddress,
    StoreStaff,
    StoreStaffRole,
    StoreStatus,
)
from ..models.user import BusinessRole, User
from ..schemas.store import (
    AreaOpenRequestCreate,
    StoreAddressCreate,
    StoreAddressUpdate,
    StoreCreate,
    StoreStaffCreate,
    StoreUpdate,
)


async def create_store(db: AsyncSession, data: StoreCreate) -> Store:
    store = Store(**data.model_dump(), status=StoreStatus.DRAFT, enabled=False)
    db.add(store)
    manager = await db.get(User, data.manager_id)
    if manager:
        manager.business_role = BusinessRole.STORE_MANAGER.value
    if data.city_manager_id:
        city_manager = await db.get(User, data.city_manager_id)
        if city_manager:
            city_manager.business_role = BusinessRole.CITY_MANAGER.value
    await db.commit()
    await db.refresh(store)
    return store


async def get_store(db: AsyncSession, store_id: int) -> Store | None:
    return await db.get(Store, store_id)


async def find_active_store_by_region(db: AsyncSession, region_id: int) -> Store | None:
    result = await db.execute(
        select(Store).where(Store.region_id == region_id, Store.enabled == True).limit(1)  # noqa: E712
    )
    return result.scalar_one_or_none()


async def list_stores(db: AsyncSession, region_id: int | None = None) -> list[Store]:
    stmt = select(Store).order_by(Store.id.desc())
    if region_id:
        stmt = stmt.where(Store.region_id == region_id)
    return list((await db.execute(stmt)).scalars().all())


async def update_store(db: AsyncSession, store: Store, data: StoreUpdate) -> Store:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(store, key, value)
    if data.manager_id:
        manager = await db.get(User, data.manager_id)
        if manager:
            manager.business_role = BusinessRole.STORE_MANAGER.value
    if data.city_manager_id:
        city_manager = await db.get(User, data.city_manager_id)
        if city_manager:
            city_manager.business_role = BusinessRole.CITY_MANAGER.value
    await db.commit()
    await db.refresh(store)
    return store


async def add_store_staff(db: AsyncSession, store_id: int, data: StoreStaffCreate) -> StoreStaff:
    staff = StoreStaff(store_id=store_id, **data.model_dump())
    db.add(staff)
    user = await db.get(User, data.user_id)
    if user:
        role_map = {
            StoreStaffRole.MANAGER: BusinessRole.STORE_MANAGER.value,
            StoreStaffRole.TECHNICIAN: BusinessRole.REPAIRER.value,
            StoreStaffRole.SECOND_RECEIVER: BusinessRole.SECOND_RECEIVER.value,
        }
        user.business_role = role_map[data.role]
    await db.commit()
    await db.refresh(staff)
    return staff


async def list_store_staff(db: AsyncSession, store_id: int) -> list[StoreStaff]:
    result = await db.execute(
        select(StoreStaff)
        .where(StoreStaff.store_id == store_id, StoreStaff.active == True)  # noqa: E712
        .order_by(StoreStaff.id)
    )
    return list(result.scalars().all())


def _clean_address_part(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value or "")).strip("-—,，。")


def _address_identity(parts: list[str]) -> tuple[str, str, str]:
    cleaned = [_clean_address_part(item) for item in parts]
    full_address = "-".join(item for item in cleaned if item)
    canonical_source = "|".join(cleaned).lower()
    canonical_key = hashlib.sha256(canonical_source.encode("utf-8")).hexdigest()
    address_code = f"ADDR-{canonical_key[:16].upper()}"
    return full_address, canonical_key, address_code


async def create_address(db: AsyncSession, data: StoreAddressCreate) -> StoreAddress:
    area = await db.get(ServiceArea, data.service_area_id)
    if not area or not area.active:
        raise ValueError("请选择有效的厦门标准服务区域")
    assignment = (
        await db.execute(
            select(ServiceAreaAssignment).where(
                ServiceAreaAssignment.service_area_id == area.id
            )
        )
    ).scalar_one_or_none()
    assigned_store_ids = {
        item for item in (
            assignment.primary_store_id if assignment else None,
            assignment.backup_store_id if assignment else None,
        ) if item
    }
    store_id = data.store_id or (assignment.primary_store_id if assignment else None)
    if not store_id:
        raise ValueError("该地址所在区域尚未分配服务门店，不能加入可下单地址库")
    if assigned_store_ids and store_id not in assigned_store_ids:
        raise ValueError("所选门店不属于该地址的服务区域分配")
    store = await db.get(Store, store_id)
    if not store or not store.enabled or store.status != StoreStatus.ACTIVE:
        raise ValueError("该地址对应的门店尚未启用")

    creator = await db.get(User, data.created_by_user_id)
    allowed_roles = {
        BusinessRole.PLATFORM_ADMIN.value,
        BusinessRole.CITY_MANAGER.value,
        BusinessRole.STORE_MANAGER.value,
        BusinessRole.REPAIRER.value,
        BusinessRole.SECOND_RECEIVER.value,
        BusinessRole.PROMOTION_MANAGER.value,
    }
    if not creator or creator.business_role not in allowed_roles:
        raise ValueError("仅平台、城市、门店、师傅或推广人员可以建立标准地址")
    owner_id = data.business_owner_user_id or (assignment.manager_id if assignment else None)
    if owner_id and not await db.get(User, owner_id):
        raise ValueError("地址业务负责人不存在")

    full_address, canonical_key, address_code = _address_identity([
        area.city,
        area.district,
        area.street,
        area.name,
        data.estate,
        data.building,
        data.unit,
        data.room,
    ])
    duplicate = (
        await db.execute(
            select(StoreAddress).where(StoreAddress.canonical_key == canonical_key)
        )
    ).scalar_one_or_none()
    if duplicate:
        raise ValueError(f"该标准地址已存在，地址编号：{duplicate.address_code}")

    address = StoreAddress(
        store_id=store.id,
        region_id=store.region_id,
        service_area_id=area.id,
        address_code=address_code,
        canonical_key=canonical_key,
        province=area.province,
        city=area.city,
        district=area.district,
        street=area.street,
        community=area.name,
        estate=_clean_address_part(data.estate),
        building=_clean_address_part(data.building),
        unit=_clean_address_part(data.unit),
        room=_clean_address_part(data.room),
        full_address=full_address,
        business_owner_user_id=owner_id,
        created_by_user_id=data.created_by_user_id,
        detail_hint=data.detail_hint,
    )
    db.add(address)
    await db.commit()
    await db.refresh(address)
    return address


async def list_addresses(
    db: AsyncSession,
    store_id: int | None = None,
    region_id: int | None = None,
    service_area_id: int | None = None,
    enabled: bool | None = None,
    q: str | None = None,
) -> list[StoreAddress]:
    stmt = select(StoreAddress).order_by(StoreAddress.id.desc())
    if store_id:
        stmt = stmt.where(StoreAddress.store_id == store_id)
    if region_id:
        stmt = stmt.where(StoreAddress.region_id == region_id)
    if service_area_id:
        stmt = stmt.where(StoreAddress.service_area_id == service_area_id)
    if enabled is not None:
        stmt = stmt.where(StoreAddress.enabled == enabled)
        if enabled:
            stmt = stmt.where(
                StoreAddress.address_code.is_not(None),
                StoreAddress.full_address.is_not(None),
            )
    if q:
        keyword = f"%{q.strip()}%"
        stmt = stmt.where(or_(
            StoreAddress.address_code.ilike(keyword),
            StoreAddress.full_address.ilike(keyword),
            StoreAddress.community.ilike(keyword),
            StoreAddress.estate.ilike(keyword),
        ))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_address(
    db: AsyncSession, address: StoreAddress, data: StoreAddressUpdate
) -> StoreAddress:
    values = data.model_dump(exclude_unset=True)
    if "store_id" in values:
        store = await db.get(Store, values["store_id"])
        if not store or not store.enabled or store.status != StoreStatus.ACTIVE:
            raise ValueError("目标门店尚未启用")
        address.store_id = store.id
        address.region_id = store.region_id
    if "business_owner_user_id" in values and values["business_owner_user_id"]:
        if not await db.get(User, values["business_owner_user_id"]):
            raise ValueError("地址业务负责人不存在")
    for key in ("business_owner_user_id", "detail_hint", "enabled"):
        if key in values:
            setattr(address, key, values[key])
    await db.commit()
    await db.refresh(address)
    return address


async def find_address(db: AsyncSession, address_id: int) -> StoreAddress | None:
    return await db.get(StoreAddress, address_id)


async def create_area_open_request(
    db: AsyncSession, data: AreaOpenRequestCreate
) -> AreaOpenRequest:
    item = AreaOpenRequest(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item
