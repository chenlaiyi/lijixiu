"""Annual service package and scheduled work-order models."""

import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PackageStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    OFFLINE = "offline"


class PackageScheduleStatus(str, enum.Enum):
    PLANNED = "planned"
    REMINDED = "reminded"
    ORDER_CREATED = "order_created"
    COMPLETED = "completed"
    OVERDUE = "overdue"


class ServicePackage(Base):
    __tablename__ = "service_packages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(50))
    service_years: Mapped[int] = mapped_column(Integer, default=1)
    annual_times: Mapped[int] = mapped_column(Integer, default=1)
    device_count: Mapped[int] = mapped_column(Integer, default=1)
    service_month: Mapped[int] = mapped_column(Integer, default=3)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PackageStatus] = mapped_column(Enum(PackageStatus), default=PackageStatus.DRAFT)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomerPackage(Base):
    __tablename__ = "customer_packages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("service_packages.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    address: Mapped[str] = mapped_column(String(500))
    contact_phone: Mapped[str] = mapped_column(String(20))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    total_times: Mapped[int] = mapped_column(Integer)
    used_times: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PackageSchedule(Base):
    __tablename__ = "package_schedules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_package_id: Mapped[int] = mapped_column(
        ForeignKey("customer_packages.id"), index=True
    )
    due_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[PackageScheduleStatus] = mapped_column(
        Enum(PackageScheduleStatus), default=PackageScheduleStatus.PLANNED
    )
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
