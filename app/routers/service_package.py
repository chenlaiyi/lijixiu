"""Service package routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
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
    data: ServicePackageCreate, db: AsyncSession = Depends(get_db)
):
    return await package_service.create_package(db, data)


@router.get("", response_model=list[ServicePackageOut])
async def list_packages(db: AsyncSession = Depends(get_db)):
    return await package_service.list_packages(db)


@router.post("/purchase", response_model=CustomerPackageOut, status_code=201)
async def buy_package(data: CustomerPackageCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await package_service.buy_package(db, data)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/customer", response_model=list[CustomerPackageOut])
async def list_customer_packages(
    user_id: int | None = None,
    store_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await package_service.list_customer_packages(db, user_id, store_id)


@router.get("/schedules", response_model=list[PackageScheduleOut])
async def list_schedules(
    customer_package_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await package_service.list_schedules(db, customer_package_id)
