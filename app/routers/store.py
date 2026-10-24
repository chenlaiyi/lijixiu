"""Store, staff, address-book, and unopened-area routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user, require_staff, require_admin, require_roles
from ..core.database import get_db
from ..models.user import User
from ..schemas.store import (
    AreaOpenRequestCreate,
    AreaOpenRequestOut,
    StoreAddressCreate,
    StoreAddressOut,
    StoreAddressUpdate,
    StoreCreate,
    StoreOut,
    StoreStaffCreate,
    StoreStaffOut,
    StoreUpdate,
)
from ..services import store as store_service

router = APIRouter(prefix="/api/v1/stores", tags=["stores"])


@router.post("", response_model=StoreOut, status_code=201)
async def create_store(
    data: StoreCreate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_admin),
):
    return await store_service.create_store(db, data)


@router.get("", response_model=list[StoreOut])
async def list_stores(
    region_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await store_service.list_stores(db, region_id)


@router.patch("/{store_id}", response_model=StoreOut)
async def update_store(
    store_id: int,
    data: StoreUpdate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_roles("platform_admin", "store_manager")),
):
    store = await store_service.get_store(db, store_id)
    if not store:
        raise HTTPException(404, "Store not found")
    return await store_service.update_store(db, store, data)


@router.post("/{store_id}/staff", response_model=StoreStaffOut, status_code=201)
async def add_staff(
    store_id: int,
    data: StoreStaffCreate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_roles("platform_admin", "store_manager")),
):
    store = await store_service.get_store(db, store_id)
    if not store:
        raise HTTPException(404, "Store not found")
    return await store_service.add_store_staff(db, store_id, data)


@router.get("/{store_id}/staff", response_model=list[StoreStaffOut])
async def list_staff(
    store_id: int,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
):
    return await store_service.list_store_staff(db, store_id)


@router.post("/addresses", response_model=StoreAddressOut, status_code=201)
async def create_address(
    data: StoreAddressCreate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_roles("platform_admin", "store_manager")),
):
    try:
        return await store_service.create_address(db, data.model_copy(update={"created_by_user_id": _staff.id}))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/addresses", response_model=list[StoreAddressOut])
async def list_addresses(
    store_id: int | None = None,
    region_id: int | None = None,
    service_area_id: int | None = None,
    enabled: bool | None = None,
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await store_service.list_addresses(
        db, store_id, region_id, service_area_id, enabled, q
    )


@router.patch("/addresses/{address_id}", response_model=StoreAddressOut)
async def update_address(
    address_id: int,
    data: StoreAddressUpdate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_roles("platform_admin", "store_manager")),
):
    address = await store_service.find_address(db, address_id)
    if not address:
        raise HTTPException(404, "Address not found")
    try:
        return await store_service.update_address(db, address, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/area-open-requests", response_model=AreaOpenRequestOut, status_code=201)
async def create_area_open_request(
    data: AreaOpenRequestCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await store_service.create_area_open_request(db, data)
