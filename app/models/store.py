"""Store, staff, and service-address models."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, enum_column


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
        enum_column(StoreStatus), default=StoreStatus.DRAFT
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
    role: Mapped[StoreStaffRole] = mapped_column(enum_column(StoreStaffRole))
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
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
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
    entrance_type: Mapped[str] = mapped_column(String(30), default='普通单元')
    entrance_name: Mapped[str] = mapped_column(String(160), default='')
    road_number: Mapped[str] = mapped_column(String(160), default='')
    raw_unit: Mapped[str] = mapped_column(String(160), default='')
    source_building_id: Mapped[str] = mapped_column(String(100), default='')
    source_unit_id: Mapped[str] = mapped_column(String(100), default='')
    source_house_id: Mapped[str] = mapped_column(String(160), default='')
    source_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    property_type: Mapped[str] = mapped_column(String(30), default='住宅')
    verification_status: Mapped[str] = mapped_column(String(100), default='人工录入，未实地核验')
    review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    collected_at: Mapped[str] = mapped_column(String(40), default='')
    source_record_json: Mapped[str] = mapped_column(Text, default='{}')
    search_aliases: Mapped[str] = mapped_column(Text, default='')
    door_number: Mapped[str | None] = mapped_column(String(240), nullable=True)
    aliases: Mapped[str] = mapped_column(Text, default="")
    source_name: Mapped[str] = mapped_column(String(80), default="")
    source_ref: Mapped[str] = mapped_column(String(240), default="")
    catalog_published: Mapped[bool] = mapped_column(Boolean, default=False)
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


class AddressCoverage(Base):
    """A store references a catalog estate, building, or individual address."""
    __tablename__ = "address_coverage"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    service_area_id: Mapped[int] = mapped_column(ForeignKey("service_areas.id"), index=True)
    building: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entrance_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    address_id: Mapped[int | None] = mapped_column(ForeignKey("store_addresses.id"), nullable=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CatalogImportBatch(Base):
    __tablename__ = 'catalog_import_batches'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    filename: Mapped[str] = mapped_column(String(240))
    file_hash: Mapped[str] = mapped_column(String(64))
    report_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
