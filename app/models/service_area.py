"""Public service-area library, store coverage, and assignment audit models."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ServiceArea(Base):
    __tablename__ = "service_areas"
    __table_args__ = (UniqueConstraint("code", name="uq_service_areas_code"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), index=True, comment="Stable area code")
    province: Mapped[str] = mapped_column(String(40), comment="Province name (Chinese)")
    city: Mapped[str] = mapped_column(String(40), index=True, comment="City name (Chinese)")
    district: Mapped[str] = mapped_column(String(60), index=True, comment="District name")
    street: Mapped[str] = mapped_column(String(80), index=True, comment="Street name")
    name: Mapped[str] = mapped_column(String(120), index=True, comment="Display name")
    area_type: Mapped[str] = mapped_column(
        String(20), default="community", index=True,
        comment="community | business | industrial",
    )
    source_name: Mapped[str] = mapped_column(
        String(120), comment="Where the area info came from (e.g. government list)"
    )
    source_url: Mapped[str] = mapped_column(
        String(500), comment="Reference URL for the source"
    )
    source_published_at: Mapped[str] = mapped_column(
        String(20), comment="Source publish date as a string"
    )
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, index=True, comment="Whether this area is active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ServiceAreaAssignment(Base):
    """Which primary / backup store and manager cover this service area."""

    __tablename__ = "service_area_assignments"
    __table_args__ = (
        UniqueConstraint("service_area_id", name="uq_service_area_assignments_area"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    service_area_id: Mapped[int] = mapped_column(
        ForeignKey("service_areas.id"), index=True
    )
    primary_store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id"), nullable=True, index=True
    )
    backup_store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id"), nullable=True, index=True
    )
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    effective_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="When this assignment becomes effective",
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True,
        comment="User id who last updated this row",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ServiceAreaAssignmentLog(Base):
    """Audit trail for service-area assignment changes."""

    __tablename__ = "service_area_assignment_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    service_area_id: Mapped[int] = mapped_column(
        ForeignKey("service_areas.id"), index=True
    )
    assignment_id: Mapped[int | None] = mapped_column(
        ForeignKey("service_area_assignments.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(
        String(30), index=True,
        comment="create | update | delete | reassign",
    )
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
