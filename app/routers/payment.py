"""Payment routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user, is_staff, require_staff, require_staff_or_self, require_admin, require_roles, require_self_or_admin
from ..core.database import get_db
from ..models.user import User, BusinessRole
from ..models.pay_order import PayProvider
from ..schemas.payment import (
    PayCallbackRequest,
    PayCreateRequest,
    PayCreateResponse,
    PayOrderOut,
    RefundCreateRequest,
    RefundOut,
)
from ..services import payment as payment_service
from ..services import safety
from ..services import wechat_pay
from ..services.wechat_pay import WeChatPayError

router = APIRouter(prefix="/api/v1/payment", tags=["payment"])
logger = logging.getLogger(__name__)


@router.post("/create", response_model=PayCreateResponse)
async def create_payment(
    data: PayCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05
):
    # 只能给自己发起支付;内部角色可代客发起
    if not is_staff(user) and data.user_id != user.id:
        raise HTTPException(403, "cannot pay for another user")
    if data.provider == PayProvider.WECHAT and (not data.js_code or data.payer_openid):
        raise HTTPException(400, "WeChat payment requires a fresh login code")
    try:
        pay_order = await payment_service.create_payment(db, data)
        intent = await payment_service.create_payment_intent(db, pay_order, data)
        return PayCreateResponse(
            pay_order_id=pay_order.id,
            pay_url=intent.pay_url,
            status="pending",
            amount=pay_order.amount,
            provider=pay_order.provider,
            payment_params=intent.payment_params or None,
        )
    except (ValueError, WeChatPayError) as e:
        raise HTTPException(400, str(e))


@router.post("/callback")
async def payment_callback(
    data: PayCallbackRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    try:
        pay_order = await payment_service.handle_callback(
            db, data.pay_order_id, data.transaction_id
        )
        return PayOrderOut.model_validate(pay_order)
    except (ValueError, safety.SafetyError) as e:
        raise HTTPException(400, str(e))


@router.post("/wechat/notify")
async def wechat_payment_notify(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    body = (await request.body()).decode("utf-8")
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        await payment_service.handle_wechat_notification(db, headers, body)
        return {"code": "SUCCESS", "message": "success"}
    except Exception:
        logger.exception("WeChat payment notification failed")
        return JSONResponse(status_code=500, content={"code": "FAIL", "message": "processing failed"})


@router.post("/wechat/refund-notify")
async def wechat_refund_notify(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    body = (await request.body()).decode("utf-8")
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        await payment_service.handle_wechat_refund_notification(db, headers, body)
        return {"code": "SUCCESS", "message": "success"}
    except Exception:
        logger.exception("WeChat refund notification failed")
        return JSONResponse(status_code=500, content={"code": "FAIL", "message": "processing failed"})


@router.get("/wechat/config-status")
async def wechat_payment_config_status(
    _staff: User = Depends(require_staff),  # 2026-10-05:配置诊断不对外
):
    return wechat_pay.config_status()


@router.post("/order/{pay_order_id}/wechat-sync", response_model=PayOrderOut)
async def sync_wechat_payment(
    pay_order_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        pay_order = await payment_service.get_pay_order(db, pay_order_id)
        if not pay_order:
            raise HTTPException(404, "pay order not found")
        require_self_or_admin(pay_order.user_id, user)
        return await payment_service.sync_wechat_payment(db, pay_order_id)
    except (ValueError, WeChatPayError, safety.SafetyError) as e:
        raise HTTPException(400, str(e))


@router.post("/refund", response_model=RefundOut)
async def create_refund(
    data: RefundCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    try:
        data.operator_id = admin.id
        return await payment_service.create_refund(db, data)
    except (ValueError, WeChatPayError) as e:
        raise HTTPException(400, str(e))


@router.post("/refund/{refund_order_id}/wechat-sync", response_model=RefundOut)
async def sync_wechat_refund(
    refund_order_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    try:
        return await payment_service.sync_wechat_refund(db, refund_order_id)
    except (ValueError, WeChatPayError) as e:
        raise HTTPException(400, str(e))


@router.get("/refunds", response_model=list[RefundOut])
async def list_refunds(
    pay_order_id: int | None = None,
    order_id: int | None = None,
    status: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),  # 2026-10-05
):
    return await payment_service.list_refunds(db, pay_order_id, order_id, status, skip, limit)


@router.get("/order/{pay_order_id}", response_model=PayOrderOut)
async def get_payment(
    pay_order_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    po = await payment_service.get_pay_order(db, pay_order_id)
    if not po:
        raise HTTPException(404, "pay order not found")
    require_staff_or_self(po.user_id, user)
    return po


@router.get("/list", response_model=list[PayOrderOut])
async def list_payments(
    order_id: int | None = None,
    user_id: int | None = None,
    status: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05
):
    # 非内部角色只能看自己的支付单
    if not is_staff(user):
        if user_id is not None and user_id != user.id:
            raise HTTPException(403, "not your payment")
        user_id = user.id
    return await payment_service.list_pay_orders(db, order_id, user_id, status, skip, limit)
