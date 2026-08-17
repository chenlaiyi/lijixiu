"""支付 Schema"""

from datetime import datetime

from typing import Any

from pydantic import BaseModel, Field

from ..models.pay_order import PayProvider, PayStatus
from ..models.refund_order import RefundStatus


class PayCreateRequest(BaseModel):
    order_id: int
    user_id: int
    amount: float = Field(gt=0)
    provider: PayProvider = PayProvider.WECHAT
    js_code: str | None = None
    payer_openid: str | None = None


class PayCreateResponse(BaseModel):
    pay_order_id: int
    pay_url: str
    status: str
    amount: float
    provider: PayProvider = PayProvider.WECHAT
    payment_params: dict[str, Any] | None = None


class PayCallbackRequest(BaseModel):
    pay_order_id: int
    transaction_id: str | None = None
    status: str = "success"    # success / fail


class PayOrderOut(BaseModel):
    id: int
    order_id: int
    user_id: int
    amount: float
    status: PayStatus
    provider: PayProvider
    transaction_id: str | None
    out_trade_no: str | None
    prepay_id: str | None
    payer_openid: str | None
    paid_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RefundCreateRequest(BaseModel):
    pay_order_id: int | None = None
    order_id: int | None = None
    amount: float = Field(gt=0)
    reason: str | None = Field(default=None, max_length=100)
    operator_id: int | None = None


class RefundOut(BaseModel):
    id: int
    pay_order_id: int
    order_id: int
    user_id: int
    amount: float
    reason: str | None
    status: RefundStatus
    out_refund_no: str | None
    refund_id: str | None
    operator_id: int | None
    success_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
