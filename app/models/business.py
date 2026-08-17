"""Cross-role, proxy-order, warranty, wage, and domestic-service models."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CustomerAddress(Base):
    __tablename__ = "customer_addresses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    contact_name: Mapped[str] = mapped_column(String(50))
    contact_phone: Mapped[str] = mapped_column(String(20))
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    service_address_id: Mapped[int | None] = mapped_column(
        ForeignKey("store_addresses.id"), nullable=True, index=True
    )
    address: Mapped[str] = mapped_column(String(500))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PhoneVerificationCode(Base):
    __tablename__ = "phone_verification_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(20), default="login")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class OrderAccessToken(Base):
    __tablename__ = "order_access_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(20), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WageRecord(Base):
    __tablename__ = "wage_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True, index=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
    repairer_id: Mapped[int] = mapped_column(ForeignKey("repairers.id"), index=True)
    employee_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    wage_mode: Mapped[str] = mapped_column(String(20), default="per_order")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    work_units: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WarrantyCertificate(Base):
    __tablename__ = "warranty_certificates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    certificate_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    service_bill_id: Mapped[int] = mapped_column(ForeignKey("service_bills.id"))
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True)
    repairer_id: Mapped[int | None] = mapped_column(ForeignKey("repairers.id"), nullable=True)
    items_json: Mapped[str] = mapped_column(Text, default="[]")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    warranty_days: Mapped[int] = mapped_column(Integer, default=0)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DomesticWorker(Base):
    __tablename__ = "domestic_workers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
    service_type: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(50))
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    years_experience: Mapped[int] = mapped_column(Integer, default=0)
    skills_json: Mapped[str] = mapped_column(Text, default="[]")
    service_regions_json: Mapped[str] = mapped_column(Text, default="[]")
    availability_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    price_min: Mapped[float] = mapped_column(Float, default=0.0)
    price_max: Mapped[float] = mapped_column(Float, default=0.0)
    id_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    health_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    training_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    rating: Mapped[float] = mapped_column(Float, default=5.0)
    service_count: Mapped[int] = mapped_column(Integer, default=0)
    intro: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DomesticDemand(Base):
    __tablename__ = "domestic_demands"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    proxy_creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    channel_manager_id_snapshot: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    service_type: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(30), default="submitted", index=True)
    contact_name: Mapped[str] = mapped_column(String(50))
    contact_phone: Mapped[str] = mapped_column(String(20))
    address: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    media_json: Mapped[str] = mapped_column(Text, default="[]")
    budget_min: Mapped[float] = mapped_column(Float, default=0.0)
    budget_max: Mapped[float] = mapped_column(Float, default=0.0)
    service_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    service_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    selected_worker_id: Mapped[int | None] = mapped_column(ForeignKey("domestic_workers.id"), nullable=True)
    is_proxy_order: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DomesticCandidate(Base):
    __tablename__ = "domestic_candidates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    demand_id: Mapped[int] = mapped_column(ForeignKey("domestic_demands.id"), index=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("domestic_workers.id"), index=True)
    proposed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="proposed", index=True)
    interview_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DomesticContract(Base):
    __tablename__ = "domestic_contracts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    demand_id: Mapped[int] = mapped_column(ForeignKey("domestic_demands.id"), unique=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("domestic_workers.id"), index=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    service_start: Mapped[date] = mapped_column(Date)
    service_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    service_fee: Mapped[float] = mapped_column(Float)
    pass_through_amount: Mapped[float] = mapped_column(Float, default=0.0)
    payment_plan: Mapped[str] = mapped_column(String(20), default="full")
    agreement_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(30), default="pending_payment", index=True)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DomesticPaymentStage(Base):
    __tablename__ = "domestic_payment_stages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("domestic_contracts.id"), index=True)
    stage_name: Mapped[str] = mapped_column(String(40))
    amount: Mapped[float] = mapped_column(Float)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    pay_order_id: Mapped[int | None] = mapped_column(ForeignKey("pay_orders.id"), nullable=True)
    payer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
