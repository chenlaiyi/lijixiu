"""Service package schemas."""

from datetime import date, datetime

from pydantic import BaseModel, Field

from ..models.service_package import PackageScheduleStatus, PackageStatus


class ServicePackageCreate(BaseModel):
    name: str
    category: str
    service_years: int = Field(ge=1)
    annual_times: int = Field(ge=1)
    device_count: int = Field(ge=1)
    service_month: int = Field(ge=1, le=12)
    price: float = Field(ge=0)
    description: str | None = None


class ServicePackageOut(BaseModel):
    id: int
    name: str
    category: str
    service_years: int
    annual_times: int
    device_count: int
    service_month: int
    price: float
    description: str | None
    status: PackageStatus
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CustomerPackageCreate(BaseModel):
    package_id: int
    user_id: int
    store_id: int
    address: str
    contact_phone: str
    start_date: date


class CustomerPackageOut(BaseModel):
    id: int
    package_id: int
    user_id: int
    store_id: int
    address: str
    contact_phone: str
    start_date: date
    end_date: date
    total_times: int
    used_times: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PackageScheduleOut(BaseModel):
    id: int
    customer_package_id: int
    due_date: date
    status: PackageScheduleStatus
    order_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
