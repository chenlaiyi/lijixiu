"""Order request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from ..models.order import OrderCategory, OrderSource, OrderStatus


class OrderCreate(BaseModel):
    customer_id: int
    region_id: int
    store_id: int | None = None
    address_book_id: int | None = None
    service_area_id: int | None = None
    estate: str | None = Field(default=None, max_length=160)
    door_number: str | None = Field(default=None, max_length=240)
    building: str | None = Field(default=None, max_length=80)
    unit: str | None = Field(default=None, max_length=80)
    room: str | None = Field(default=None, max_length=80)
    respect_service_area: bool = True
    category: OrderCategory = OrderCategory.OTHER
    description: str = Field(min_length=1, max_length=2000)
    media_json: str | None = None
    address: str = Field(min_length=1, max_length=500)
    contact_phone: str | None = None
    source: OrderSource = OrderSource.REPAIR
    scheduled_time: datetime | None = None
    created_by_user_id: int | None = None
    proxy_creator_id: int | None = None
    referrer_user_id: int | None = None
    channel_manager_id_snapshot: int | None = None
    is_proxy_order: bool = False
    proxy_reason: str | None = Field(default=None, max_length=50)
    customer_name_snapshot: str | None = Field(default=None, max_length=50)
    customer_phone_snapshot: str | None = Field(default=None, max_length=20)
    customer_address_snapshot: str | None = Field(default=None, max_length=500)


class OrderAssign(BaseModel):
    repairer_id: int


class StoreSelfServiceRequest(BaseModel):
    manager_id: int
    skills: str = "门店综合服务"


class OrderUpdate(BaseModel):
    repairer_id: int | None = None
    assigned_repairer_id: int | None = None
    status: OrderStatus | None = None
    price: float | None = Field(None, ge=0)
    technician_wage_amount: float | None = Field(None, ge=0)
    commissionable_amount: float | None = Field(None, ge=0)
    address_review_status: str | None = None


class OrderTransition(BaseModel):
    to_status: OrderStatus
    operator_type: str = "customer"
    operator_id: int | None = None
    remark: str | None = None


class StoreReviewRequest(BaseModel):
    technician_wage_amount: float = Field(ge=0)
    wage_mode: str = Field(default="per_order", pattern="^(per_order|monthly)$")
    remark: str | None = None


class OrderRatingRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    remark: str | None = None


class OrderOut(BaseModel):
    id: int
    customer_id: int
    created_by_user_id: int | None
    proxy_creator_id: int | None
    referrer_user_id: int | None
    channel_manager_id_snapshot: int | None
    is_proxy_order: bool
    proxy_reason: str | None
    claim_status: str
    claimed_by_user_id: int | None
    claimed_at: datetime | None
    customer_name_snapshot: str | None
    customer_phone_snapshot: str | None
    customer_address_snapshot: str | None
    repairer_id: int | None
    assigned_repairer_id: int | None
    assigned_at: datetime | None
    store_id: int | None
    source: OrderSource
    region_id: int
    estate: str | None
    door_number: str | None = None
    building: str | None
    unit: str | None
    room: str | None
    address_book_id: int | None
    address_code_snapshot: str | None
    address_owner_user_id: int | None
    service_area_id: int | None
    service_area_assignment_id: int | None
    service_area_manager_id: int | None
    service_area_district_snapshot: str | None
    service_area_street_snapshot: str | None
    service_area_name_snapshot: str | None
    category: OrderCategory
    description: str
    media_json: str | None
    address: str
    contact_phone: str | None
    address_changed: bool
    address_review_status: str
    price: float
    commissionable_amount: float
    status: OrderStatus
    scheduled_time: datetime | None
    paid_at: datetime | None
    completed_at: datetime | None
    store_reviewed_at: datetime | None
    technician_wage_amount: float
    wage_mode: str
    paid_amount: float
    latest_payer_user_id: int | None
    service_confirmation_method: str | None
    service_confirmation_note: str | None
    service_confirmed_at: datetime | None
    risk_review_required: bool
    settlement_status: str
    rating: int | None
    rating_remark: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
