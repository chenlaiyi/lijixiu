"""Service package services."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.service_package import (
    CustomerPackage,
    PackageSchedule,
    PackageStatus,
    ServicePackage,
)
from ..schemas.service_package import CustomerPackageCreate, ServicePackageCreate


async def create_package(db: AsyncSession, data: ServicePackageCreate) -> ServicePackage:
    package = ServicePackage(**data.model_dump(), status=PackageStatus.ACTIVE, enabled=True)
    db.add(package)
    await db.commit()
    await db.refresh(package)
    return package


async def list_packages(db: AsyncSession, enabled_only: bool = True) -> list[ServicePackage]:
    stmt = select(ServicePackage).order_by(ServicePackage.id.desc())
    if enabled_only:
        stmt = stmt.where(ServicePackage.enabled == True)  # noqa: E712
    return list((await db.execute(stmt)).scalars().all())


async def buy_package(db: AsyncSession, data: CustomerPackageCreate) -> CustomerPackage:
    package = await db.get(ServicePackage, data.package_id)
    if not package or not package.enabled:
        raise ValueError("Service package is not available")

    end_date = data.start_date.replace(year=data.start_date.year + package.service_years)
    total_times = package.service_years * package.annual_times * package.device_count
    customer_package = CustomerPackage(
        package_id=data.package_id,
        user_id=data.user_id,
        store_id=data.store_id,
        address=data.address,
        contact_phone=data.contact_phone,
        start_date=data.start_date,
        end_date=end_date,
        total_times=total_times,
    )
    db.add(customer_package)
    await db.flush()

    for year_index in range(package.service_years):
        due = date(data.start_date.year + year_index, package.service_month, 1)
        for _ in range(package.annual_times * package.device_count):
            db.add(PackageSchedule(customer_package_id=customer_package.id, due_date=due))

    await db.commit()
    await db.refresh(customer_package)
    return customer_package


async def list_customer_packages(
    db: AsyncSession, user_id: int | None = None, store_id: int | None = None
) -> list[CustomerPackage]:
    stmt = select(CustomerPackage).order_by(CustomerPackage.id.desc())
    if user_id:
        stmt = stmt.where(CustomerPackage.user_id == user_id)
    if store_id:
        stmt = stmt.where(CustomerPackage.store_id == store_id)
    return list((await db.execute(stmt)).scalars().all())


async def list_schedules(
    db: AsyncSession, customer_package_id: int | None = None
) -> list[PackageSchedule]:
    stmt = select(PackageSchedule).order_by(PackageSchedule.due_date.asc())
    if customer_package_id:
        stmt = stmt.where(PackageSchedule.customer_package_id == customer_package_id)
    return list((await db.execute(stmt)).scalars().all())
