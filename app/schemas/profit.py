"""分润 Schema"""

from datetime import datetime

from pydantic import BaseModel

from ..models.profit_share import ProfitRole, ProfitStatus


class ProfitShareOut(BaseModel):
    id: int
    order_id: int
    user_id: int | None
    store_id: int | None
    role_type: ProfitRole
    amount: float
    ratio: float
    status: ProfitStatus
    settled_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfitSummary(BaseModel):
    """用户/订单分润汇总"""
    order_id: int
    order_price: float
    total_distributed: float
    items: list[ProfitShareOut]
