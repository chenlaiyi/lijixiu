"""Store, staff, and service-address models."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class StoreStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class StoreStaffRole(str, enum.Enum):
    MANAGER = "manager"
    TECHNICIAN = "technician"
    SECOND_RECEIVER = "second_receiver"


class Store(Base):
    """Regional store operated by the platform and a store manager."""

    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    city_manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True,
        comment="City manager (admin) user id for this store",
    )
    manager_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True,
        comment="Store manager user id",
    )
    default_second_receiver_id: Mapped[int | None] = mapped_column(
        ForeignKey("repairers.id"), nullable=True,
        comment="Default secondary receiver repairer id (for two-person delivery)",
    )
    status: Mapped[StoreStatus] = mapped_column(
        Enum(StoreStatus), default=StoreStatus.DRAFT
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class StoreStaff(Base):
    """Users / repairers assigned to a store with a given role."""

    __tablename__ = "store_staff"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    repairer_id: Mapped[int | None] = mapped_column(
        ForeignKey("repairers.id"), nullable=True,
        comment="Linked repairer id if this staff member is also a repairer",
    )
    role: Mapped[StoreStaffRole] = mapped_column(Enum(StoreStaffRole))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class StoreAddress(Base):
    """An opened service-address entry bound to a store."""

    __tablename__ = "store_addresses"
    __table_args__ = (
        UniqueConstraint("address_code", name="uq_store_addresses_code"),
        UniqueConstraint("canonical_key", name="uq_store_addresses_canonical_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    service_area_id: Mapped[int | None] = mapped_column(
        ForeignKey("service_areas.id"), nullable=True, index=True
    )
    address_code: Mapped[str | None] = mapped_column(
        String(40), nullable=True, index=True
    )
    canonical_key: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True,
        comment="Hash/canonical key used for dedupe",
    )
    province: Mapped[str] = mapped_column(String(40), comment="Province name (Chinese)")
    city: Mapped[str] = mapped_column(String(80), default="", comment="City name")
    district: Mapped[str] = mapped_column(String(80), default="", comment="District name")
    street: Mapped[str] = mapped_column(String(120), default="", comment="Street name")
    community: Mapped[str] = mapped_column(
        String(160), index=True, comment="Community / village name"
    )
    estate: Mapped[str] = mapped_column(
        String(160), default="", comment="Estate / building complex name"
    )
    building: Mapped[str] = mapped_column(
        String(80), default="", comment="Building number"
    )
    unit: Mapped[str] = mapped_column(
        String(80), default="", comment="Unit number"
    )
    room: Mapped[str] = mapped_column(
        String(80), default="", comment="Room number"
    )
    full_address: Mapped[str | None] = mapped_column(
        String(500), nullable=True, index=True
    )
    business_owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    detail_hint: Mapped[str | None] = mapped_column(
        String(300), nullable=True, comment="Free-form delivery hint"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class AreaOpenRequest(Base):
    """Lead captured when a customer address is not opened yet."""

    __tablename__ = "area_open_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address_text: Mapped[str] = mapped_column(String(500))
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", comment="pending | opened | closed"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
