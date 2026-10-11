"""财务/分润路由"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user, is_staff, require_staff
from ..core.database import get_db
from ..models.user import User
from ..schemas.profit import ProfitShareOut, ProfitSummary
from ..services import order as order_service
from ..services import profit as profit_service

router = APIRouter(prefix="/api/v1/finance", tags=["财务分润"])


@router.get("/profit/order/{order_id}", response_model=ProfitSummary)
async def get_order_profit(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),  # 2026-10-05:分润仅内部可见
):
    """查看订单分润明细"""
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")

    items = await profit_service.get_order_profits(db, order_id)

    distributed = sum(item.amount for item in items) if items else 0.0

    return ProfitSummary(
        order_id=order_id,
        order_price=order.price,
        total_distributed=distributed,
        items=[
            ProfitShareOut.model_validate(item) for item in items
        ],
    )


@router.get("/profit/user/{user_id}", response_model=list[ProfitShareOut])
async def get_user_profits(
    user_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05:本人或内部
):
    if not is_staff(user) and user_id != user.id:
        raise HTTPException(403, "not your profit")
    """查看用户全部分润记录"""
    items = await profit_service.get_user_profits(db, user_id, skip, limit)
    return [ProfitShareOut.model_validate(item) for item in items]
