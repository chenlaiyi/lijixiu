"""Wallet schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from ..models.ledger import LedgerType
from ..models.withdrawal import WithdrawalStatus


class WalletOut(BaseModel):
    id: int
    user_id: int
    available_balance: float
    frozen_balance: float
    total_income: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LedgerOut(BaseModel):
    id: int
    wallet_id: int
    user_id: int
    type: LedgerType
    amount: float
    balance_after: float
    reference_type: str | None
    reference_id: int | None
    remark: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WithdrawalCreate(BaseModel):
    amount: float = Field(gt=0)
    remark: str | None = None


class WithdrawalReview(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    remark: str | None = None
    payout_method: str = Field(default="manual", pattern="^(manual|wechat)$")


class WithdrawalOut(BaseModel):
    id: int
    user_id: int
    wallet_id: int
    amount: float
    status: WithdrawalStatus
    remark: str | None
    payout_provider: str
    payout_status: str
    transfer_out_bill_no: str | None
    transfer_bill_no: str | None
    payout_at: datetime | None
    reviewed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
