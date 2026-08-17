"""Payment routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
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


@router.post("/create", response_model=PayCreateResponse)
async def create_payment(
    data: PayCreateRequest,
    db: AsyncSession = Depends(get_db),
):
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
    except Exception as e:
        return JSONResponse(status_code=500, content={"code": "FAIL", "message": str(e)})


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
    except Exception as e:
        return JSONResponse(status_code=500, content={"code": "FAIL", "message": str(e)})


@router.get("/wechat/config-status")
async def wechat_payment_config_status():
    return wechat_pay.config_status()


@router.post("/order/{pay_order_id}/wechat-sync", response_model=PayOrderOut)
async def sync_wechat_payment(
    pay_order_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await payment_service.sync_wechat_payment(db, pay_order_id)
    except (ValueError, WeChatPayError, safety.SafetyError) as e:
        raise HTTPException(400, str(e))


@router.post("/refund", response_model=RefundOut)
async def create_refund(
    data: RefundCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await payment_service.create_refund(db, data)
    except (ValueError, WeChatPayError) as e:
        raise HTTPException(400, str(e))


@router.post("/refund/{refund_order_id}/wechat-sync", response_model=RefundOut)
async def sync_wechat_refund(
    refund_order_id: int,
    db: AsyncSession = Depends(get_db),
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
):
    return await payment_service.list_refunds(db, pay_order_id, order_id, status, skip, limit)


@router.get("/order/{pay_order_id}", response_model=PayOrderOut)
async def get_payment(
    pay_order_id: int,
    db: AsyncSession = Depends(get_db),
):
    po = await payment_service.get_pay_order(db, pay_order_id)
    if not po:
        raise HTTPException(404, "pay order not found")
    return po


@router.get("/list", response_model=list[PayOrderOut])
async def list_payments(
    order_id: int | None = None,
    user_id: int | None = None,
    status: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return await payment_service.list_pay_orders(db, order_id, user_id, status, skip, limit)
