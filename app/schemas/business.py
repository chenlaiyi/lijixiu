"""Schemas for addresses, proxy access, wages, warranties, and domestic services."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class AddressCreate(BaseModel):
    user_id: int
    contact_name: str = Field(min_length=1, max_length=50)
    contact_phone: str = Field(min_length=7, max_length=20)
    service_address_id: int | None = None
    service_area_id: int | None = None
    estate: str | None = Field(default=None, max_length=160)
    door_number: str | None = Field(default=None, max_length=240)
    is_default: bool = False


class AddressUpdate(BaseModel):
    service_address_id: int | None = None
    service_area_id: int | None = None
    estate: str | None = Field(default=None, max_length=160)
    door_number: str | None = Field(default=None, max_length=240)
    contact_name: str | None = Field(default=None, min_length=1, max_length=50)
    contact_phone: str | None = Field(default=None, min_length=7, max_length=20)
    is_default: bool | None = None
    enabled: bool | None = None


class AddressOut(AddressCreate):
    city: str = ""
    district: str = ""
    id: int
    region_id: int | None
    address: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class AccessTokenRequest(BaseModel):
    created_by_user_id: int | None = None


class AccessTokenOut(BaseModel):
    token: str
    purpose: str
    order_id: int
    expires_at: datetime
    page: str
    code_url: str


class ClaimOrderRequest(BaseModel):
    token: str = Field(min_length=16, max_length=100)
    user_id: int
    verification_phone: str | None = Field(default=None, max_length=20)


class ClaimOrderOut(BaseModel):
    order_id: int
    action: str
    claim_status: str
    message: str


class WageOut(BaseModel):
    id: int
    order_id: int
    store_id: int | None
    repairer_id: int
    employee_user_id: int
    wage_mode: str
    amount: float
    work_units: float
    status: str
    reviewed_by_user_id: int | None
    remark: str | None
    paid_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class PayrollLine(BaseModel):
    employee_user_id: int
    amount: float = Field(gt=0)
    remark: str | None = None


class PayrollCreate(BaseModel):
    month: str = Field(pattern="^\\d{4}-(0[1-9]|1[0-2])$")
    store_id: int
    manager_id: int
    lines: list[PayrollLine] = Field(min_length=1)


class PayrollPayRequest(BaseModel):
    store_id: int
    manager_id: int


class WarrantyOut(BaseModel):
    id: int
    certificate_no: str
    order_id: int
    customer_id: int
    service_bill_id: int
    store_id: int | None
    repairer_id: int | None
    items_json: str
    amount: float
    warranty_days: int
    starts_at: datetime
    expires_at: datetime
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}


class DomesticWorkerCreate(BaseModel):
    user_id: int | None = None
    store_id: int | None = None
    service_type: str = Field(pattern="^(maternity|nanny)$")
    name: str = Field(min_length=1, max_length=50)
    avatar: str | None = None
    years_experience: int = Field(default=0, ge=0, le=60)
    skills_json: str = "[]"
    service_regions_json: str = "[]"
    availability_text: str | None = None
    price_min: float = Field(default=0, ge=0)
    price_max: float = Field(default=0, ge=0)
    id_verified: bool = False
    health_verified: bool = False
    training_verified: bool = False
    intro: str | None = None
    active: bool = True


class DomesticWorkerUpdate(BaseModel):
    store_id: int | None = None
    name: str | None = None
    avatar: str | None = None
    years_experience: int | None = Field(default=None, ge=0, le=60)
    skills_json: str | None = None
    service_regions_json: str | None = None
    availability_text: str | None = None
    price_min: float | None = Field(default=None, ge=0)
    price_max: float | None = Field(default=None, ge=0)
    id_verified: bool | None = None
    health_verified: bool | None = None
    training_verified: bool | None = None
    intro: str | None = None
    active: bool | None = None


class DomesticWorkerOut(DomesticWorkerCreate):
    id: int
    rating: float
    service_count: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class DomesticDemandCreate(BaseModel):
    customer_id: int
    created_by_user_id: int | None = None
    proxy_creator_id: int | None = None
    store_id: int | None = None
    region_id: int
    service_type: str = Field(pattern="^(maternity|nanny)$")
    contact_name: str = Field(min_length=1, max_length=50)
    contact_phone: str = Field(min_length=7, max_length=20)
    address: str = Field(min_length=1, max_length=500)
    description: str | None = None
    detail_json: str = "{}"
    media_json: str = "[]"
    budget_min: float = Field(default=0, ge=0)
    budget_max: float = Field(default=0, ge=0)
    service_start: date | None = None
    service_end: date | None = None
    is_proxy_order: bool = False


class DomesticDemandUpdate(BaseModel):
    status: str | None = None
    store_id: int | None = None
    description: str | None = None
    detail_json: str | None = None
    media_json: str | None = None
    budget_min: float | None = Field(default=None, ge=0)
    budget_max: float | None = Field(default=None, ge=0)
    service_start: date | None = None
    service_end: date | None = None


class DomesticDemandOut(DomesticDemandCreate):
    id: int
    status: str
    selected_worker_id: int | None
    channel_manager_id_snapshot: int | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class CandidateCreate(BaseModel):
    worker_id: int
    proposed_by_user_id: int | None = None
    interview_at: datetime | None = None
    trial_at: datetime | None = None
    note: str | None = None


class CandidateUpdate(BaseModel):
    status: str = Field(pattern="^(proposed|interested|interview|trial|selected|rejected|withdrawn)$")
    interview_at: datetime | None = None
    trial_at: datetime | None = None
    note: str | None = None


class CandidateOut(CandidateCreate):
    id: int
    demand_id: int
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}


class PaymentStageInput(BaseModel):
    stage_name: str = Field(min_length=1, max_length=40)
    amount: float = Field(gt=0)
    due_date: date | None = None


class ContractCreate(BaseModel):
    worker_id: int
    created_by_user_id: int
    service_start: date
    service_end: date | None = None
    service_fee: float = Field(gt=0)
    pass_through_amount: float = Field(default=0, ge=0)
    payment_plan: str = Field(default="full", pattern="^(full|deposit_final|monthly|custom)$")
    agreement_json: str = "{}"
    payment_stages: list[PaymentStageInput] = Field(default_factory=list)


class ContractOut(BaseModel):
    id: int
    demand_id: int
    order_id: int
    customer_id: int
    worker_id: int
    store_id: int | None
    created_by_user_id: int
    service_start: date
    service_end: date | None
    service_fee: float
    pass_through_amount: float
    payment_plan: str
    agreement_json: str
    status: str
    terminated_at: datetime | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class PaymentStageOut(BaseModel):
    id: int
    contract_id: int
    stage_name: str
    amount: float
    due_date: date | None
    pay_order_id: int | None
    payer_user_id: int | None
    status: str
    paid_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class StagePaymentRequest(BaseModel):
    user_id: int
    provider: str = Field(default="wechat", pattern="^(mock|wechat)$")
    js_code: str | None = None


class ContractActionRequest(BaseModel):
    operator_id: int
    action: str = Field(pattern="^(start|complete|terminate|complaint)$")
    remark: str | None = None
