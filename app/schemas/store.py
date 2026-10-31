"""Store management schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from ..models.store import StoreStaffRole, StoreStatus


class StoreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    region_id: int
    manager_id: int
    city_manager_id: int | None = None
    default_second_receiver_id: int | None = None
    remark: str | None = None


class StoreUpdate(BaseModel):
    region_id: int | None = None
    name: str | None = Field(None, min_length=1, max_length=100)
    manager_id: int | None = None
    city_manager_id: int | None = None
    default_second_receiver_id: int | None = None
    status: StoreStatus | None = None
    enabled: bool | None = None
    remark: str | None = None


class StoreOut(BaseModel):
    id: int
    name: str
    region_id: int
    city_manager_id: int | None
    manager_id: int
    default_second_receiver_id: int | None
    status: StoreStatus
    enabled: bool
    remark: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StoreStaffCreate(BaseModel):
    user_id: int
    repairer_id: int | None = None
    role: StoreStaffRole


class StoreStaffOut(BaseModel):
    id: int
    store_id: int
    user_id: int
    repairer_id: int | None
    role: StoreStaffRole
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class StoreAddressCreate(BaseModel):
    service_area_id: int
    store_id: int | None = None
    estate: str = Field(min_length=1, max_length=160)
    door_number: str | None = Field(default=None, max_length=240)
    building: str = Field(default="", max_length=80)
    unit: str = Field(default="", max_length=80)
    room: str = Field(default="", max_length=80)
    business_owner_user_id: int | None = None
    created_by_user_id: int
    detail_hint: str | None = Field(default=None, max_length=300)
    aliases: str = Field(default="", max_length=4000)
    source_name: str = Field(default="", max_length=80)
    source_ref: str = Field(default="", max_length=240)
    catalog_published: bool = True


class StoreAddressUpdate(BaseModel):
    service_area_id: int | None = None
    building: str | None = Field(default=None, max_length=80)
    unit: str | None = Field(default=None, max_length=80)
    room: str | None = Field(default=None, max_length=80)
    aliases: str | None = Field(default=None, max_length=4000)
    source_name: str | None = Field(default=None, max_length=80)
    source_ref: str | None = Field(default=None, max_length=240)
    catalog_published: bool | None = None
    estate: str | None = Field(default=None, min_length=1, max_length=160)
    door_number: str | None = Field(default=None, min_length=1, max_length=240)
    store_id: int | None = None
    business_owner_user_id: int | None = None
    detail_hint: str | None = Field(default=None, max_length=300)
    enabled: bool | None = None


class StoreAddressOut(BaseModel):
    aliases: str = ""
    source_name: str = ""
    source_ref: str = ""
    catalog_published: bool = False
    id: int
    store_id: int
    region_id: int
    service_area_id: int | None
    address_code: str | None
    canonical_key: str | None
    province: str
    city: str
    district: str
    street: str
    community: str
    estate: str
    door_number: str | None = None
    building: str
    unit: str
    room: str
    full_address: str | None
    business_owner_user_id: int | None
    created_by_user_id: int | None
    detail_hint: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AreaOpenRequestCreate(BaseModel):
    user_id: int | None = None
    phone: str | None = None
    address_text: str
    category: str | None = None
    remark: str | None = None


class AreaOpenRequestOut(BaseModel):
    id: int
    user_id: int | None
    phone: str | None
    address_text: str
    category: str | None
    status: str
    remark: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class StoreCoverageUpdate(BaseModel):
    estates: list[str] = Field(default_factory=list, max_length=500)
