"""订单流转日志 Schema"""

from datetime import datetime

from pydantic import BaseModel

from ..models.order_log import OperatorType


class OrderLogOut(BaseModel):
    id: int
    order_id: int
    from_status: str
    to_status: str
    operator_type: OperatorType
    operator_id: int | None
    remark: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
