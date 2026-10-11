"""Service package routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user, is_staff, require_staff
from ..core.database import get_db
from ..models.user import User
from ..schemas.service_package import (
    CustomerPackageCreate,
    CustomerPackageOut,
    PackageScheduleOut,
    ServicePackageCreate,
    ServicePackageOut,
)
from ..services import service_package as package_service

router = APIRouter(prefix="/api/v1/service-packages", tags=["service packages"])


@router.post("", response_model=ServicePackageOut, status_code=201)
async def create_package(
    data: ServicePackageCreate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
):
    return await package_service.create_package(db, data)


@router.get("", response_model=list[ServicePackageOut])
async def list_packages(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await package_service.list_packages(db)


@router.post("/purchase", response_model=CustomerPackageOut, status_code=201)
async def buy_package(
    data: CustomerPackageCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not is_staff(user) and data.user_id != user.id:
        raise HTTPException(403, "cannot purchase for another user")
    try:
        return await package_service.buy_package(db, data)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/customer", response_model=list[CustomerPackageOut])
async def list_customer_packages(
    user_id: int | None = None,
    store_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not is_staff(user):
        if user_id is not None and user_id != user.id:
            raise HTTPException(403, "not your package")
        user_id = user.id
    return await package_service.list_customer_packages(db, user_id, store_id)


@router.get("/schedules", response_model=list[PackageScheduleOut])
async def list_schedules(
    customer_package_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await package_service.list_schedules(db, customer_package_id)
