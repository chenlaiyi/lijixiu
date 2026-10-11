"""Order model and workflow state machine."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, enum_column


class OrderStatus(str, enum.Enum):
    CREATED = "created"
    STORE_PENDING = "store_pending"
    STORE_ACCEPTED = "store_accepted"
    DISPATCHED = "dispatched"
    REPAIRER_ACCEPTED = "repairer_accepted"
    SERVICING = "servicing"
    BILL_SUBMITTED = "bill_submitted"
    BILL_RETURNED = "bill_returned"
    WAIT_PAYMENT = "wait_payment"
    PAID = "paid"
    PAID_PENDING_REVIEW = "paid_pending_review"
    STORE_REVIEWED = "store_reviewed"
    COMPLETED = "completed"
    REFUNDING = "refunding"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"

    # Compatibility with the first prototype.
    ASSIGNED = "assigned"
    ACCEPTED = "accepted"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"


class OrderSource(str, enum.Enum):
    REPAIR = "repair"
    PACKAGE = "package"
    AFTER_SALES = "after_sales"
    MATERNITY = "maternity"
    NANNY = "nanny"


ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.CREATED: {
        OrderStatus.STORE_PENDING,
        OrderStatus.ASSIGNED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.STORE_PENDING: {
        OrderStatus.STORE_ACCEPTED,
        OrderStatus.DISPATCHED,
        OrderStatus.ASSIGNED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.STORE_ACCEPTED: {OrderStatus.DISPATCHED, OrderStatus.CANCELLED},
    OrderStatus.DISPATCHED: {OrderStatus.REPAIRER_ACCEPTED, OrderStatus.CANCELLED},
    OrderStatus.REPAIRER_ACCEPTED: {OrderStatus.SERVICING, OrderStatus.CANCELLED},
    OrderStatus.SERVICING: {
        OrderStatus.BILL_SUBMITTED,
        OrderStatus.WAIT_PAYMENT,
        OrderStatus.CANCELLED,
    },
    OrderStatus.BILL_SUBMITTED: {
        OrderStatus.BILL_RETURNED,
        OrderStatus.WAIT_PAYMENT,
        OrderStatus.CANCELLED,
    },
    OrderStatus.BILL_RETURNED: {OrderStatus.BILL_SUBMITTED, OrderStatus.CANCELLED},
    OrderStatus.WAIT_PAYMENT: {OrderStatus.PAID, OrderStatus.CANCELLED},
    OrderStatus.PAID: {OrderStatus.PAID_PENDING_REVIEW, OrderStatus.COMPLETED, OrderStatus.REFUNDING, OrderStatus.REFUNDED},
    OrderStatus.PAID_PENDING_REVIEW: {OrderStatus.STORE_REVIEWED, OrderStatus.COMPLETED, OrderStatus.REFUNDING, OrderStatus.REFUNDED},
    OrderStatus.STORE_REVIEWED: {OrderStatus.COMPLETED, OrderStatus.REFUNDING, OrderStatus.REFUNDED},
    OrderStatus.COMPLETED: {OrderStatus.REFUNDING, OrderStatus.REFUNDED},
    OrderStatus.REFUNDING: {OrderStatus.REFUNDED},
    OrderStatus.REFUNDED: set(),
    OrderStatus.CANCELLED: set(),

    # Prototype compatibility.
    OrderStatus.ASSIGNED: {
        OrderStatus.ACCEPTED,
        OrderStatus.REPAIRER_ACCEPTED,
        OrderStatus.ASSIGNED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.ACCEPTED: {OrderStatus.SERVICING, OrderStatus.CANCELLED},
    OrderStatus.PENDING: {
        OrderStatus.STORE_PENDING,
        OrderStatus.ASSIGNED,
        OrderStatus.ACCEPTED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.IN_PROGRESS: {
        OrderStatus.WAIT_PAYMENT,
        OrderStatus.COMPLETED,
        OrderStatus.CANCELLED,
    },
}


def validate_transition(from_status: OrderStatus, to_status: OrderStatus) -> bool:
    return to_status in ALLOWED_TRANSITIONS.get(from_status, set())


class OrderCategory(str, enum.Enum):
    APPLIANCE = "appliance"
    DOOR_WINDOW = "door_window"
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    FURNITURE_INSTALL = "furniture_install"
    APPLIANCE_INSTALL = "appliance_install"
    PIPE_DREDGE = "pipe_dredge"
    CARPENTRY = "carpentry"
    LOCKSMITH = "locksmith"
    PAINTING = "painting"
    CLEANING = "cleaning"
    OTHER = "other"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    proxy_creator_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    referrer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    channel_manager_id_snapshot: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    is_proxy_order: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    proxy_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    claim_status: Mapped[str] = mapped_column(String(20), default="not_required", index=True)
    claimed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    customer_name_snapshot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    customer_phone_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    customer_address_snapshot: Mapped[str | None] = mapped_column(String(500), nullable=True)
    repairer_id: Mapped[int | None] = mapped_column(ForeignKey("repairers.id"), nullable=True)
    assigned_repairer_id: Mapped[int | None] = mapped_column(
        ForeignKey("repairers.id"), nullable=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
    source: Mapped[OrderSource] = mapped_column(enum_column(OrderSource), default=OrderSource.REPAIR)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    address_book_id: Mapped[int | None] = mapped_column(
        ForeignKey("store_addresses.id"), nullable=True
    )
    address_code_snapshot: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address_owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    service_area_id: Mapped[int | None] = mapped_column(
        ForeignKey("service_areas.id"), nullable=True, index=True
    )
    service_area_assignment_id: Mapped[int | None] = mapped_column(nullable=True)
    service_area_manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    service_area_district_snapshot: Mapped[str | None] = mapped_column(
        String(60), nullable=True
    )
    service_area_street_snapshot: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    service_area_name_snapshot: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    category: Mapped[OrderCategory] = mapped_column(enum_column(OrderCategory), default=OrderCategory.OTHER)
    description: Mapped[str] = mapped_column(Text)
    media_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str] = mapped_column(String(500))
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    address_review_status: Mapped[str] = mapped_column(String(20), default="none")

    price: Mapped[float] = mapped_column(Float, default=0.0)
    commissionable_amount: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[OrderStatus] = mapped_column(enum_column(OrderStatus), default=OrderStatus.CREATED)
    scheduled_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    store_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    technician_wage_amount: Mapped[float] = mapped_column(Float, default=0.0)
    wage_mode: Mapped[str] = mapped_column(String(20), default="per_order")
    paid_amount: Mapped[float] = mapped_column(Float, default=0.0)
    latest_payer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    service_confirmation_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    service_confirmation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    risk_review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    settlement_status: Mapped[str] = mapped_column(String(20), default="pending")
    rating: Mapped[int | None] = mapped_column(nullable=True)
    rating_remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
