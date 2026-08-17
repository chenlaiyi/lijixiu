"""Service bill schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from ..models.service_bill import ServiceBillStatus


class ServiceBillCreate(BaseModel):
    repairer_id: int
    title: str = "服务项目单据"
    items_json: str = "[]"
    amount: float = Field(ge=0)
    warranty_days: int = Field(0, ge=0)
    media_json: str | None = None
    save_as_draft: bool = False
    confirmation_method: str | None = Field(
        default=None, pattern="^(face_to_face|phone|wechat|other)$"
    )
    confirmation_note: str | None = Field(default=None, max_length=500)


class ServiceBillReturn(BaseModel):
    reason: str | None = None


class ServiceBillOut(BaseModel):
    id: int
    order_id: int
    repairer_id: int
    title: str
    items_json: str
    amount: float
    warranty_days: int
    media_json: str | None
    status: ServiceBillStatus
    return_reason: str | None
    revision: int
    confirmation_method: str | None
    confirmation_note: str | None
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
