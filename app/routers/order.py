"""订单路由 v2"""

import json
import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.database import get_db
from ..schemas.order import (
    OrderAssign,
    OrderCreate,
    OrderOut,
    OrderRatingRequest,
    StoreSelfServiceRequest,
    StoreReviewRequest,
    OrderTransition,
    OrderUpdate,
)
from ..schemas.order_log import OrderLogOut
from ..schemas.service_bill import ServiceBillCreate, ServiceBillOut, ServiceBillReturn
from ..services import order as order_service
from ..services import service_bill as bill_service
from ..services import user as user_service

router = APIRouter(prefix="/api/v1/orders", tags=["订单"])

_MAX_MEDIA_SIZE = 80 * 1024 * 1024
_EXT_BY_CONTENT_TYPE = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/x-m4a": ".m4a",
    "audio/wav": ".wav",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
}
_DEFAULT_EXT_BY_MEDIA_TYPE = {
    "audio": ".mp3",
    "image": ".jpg",
    "video": ".mp4",
}


def _upload_root() -> Path:
    root = Path(settings.UPLOAD_DIR)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def _media_list(order) -> list[dict]:
    if not order.media_json:
        return []
    try:
        data = json.loads(order.media_json)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _safe_ext(file: UploadFile, media_type: str) -> str:
    ext = Path(file.filename or "").suffix.lower()
    if ext in {".mp3", ".m4a", ".aac", ".wav", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".mp4", ".mov"}:
        return ext
    return _EXT_BY_CONTENT_TYPE.get(file.content_type or "", _DEFAULT_EXT_BY_MEDIA_TYPE.get(media_type, ".bin"))


@router.post("", response_model=OrderOut, status_code=201)
async def create_order(data: OrderCreate, db: AsyncSession = Depends(get_db)):
    customer = await user_service.get_user(db, data.customer_id)
    if not customer:
        raise HTTPException(404, "客户不存在")
    try:
        return await order_service.create_order(db, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("", response_model=list[OrderOut])
async def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    customer_id: int | None = None,
    repairer_id: int | None = None,
    assigned_repairer_id: int | None = None,
    status: str | None = None,
    region_id: int | None = None,
    store_id: int | None = None,
    is_proxy_order: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await order_service.list_orders(
        db, skip, limit, customer_id, repairer_id,
        assigned_repairer_id, status, region_id, store_id, is_proxy_order,
    )


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: int, db: AsyncSession = Depends(get_db)):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    return order


@router.post("/{order_id}/media", response_model=OrderOut)
async def upload_order_media(
    order_id: int,
    media_type: str = Form(...),
    duration: int | None = Form(None),
    name: str | None = Form(None),
    uploader_id: int | None = Form(None),
    original_name: str | None = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    if media_type not in ("audio", "image", "video"):
        raise HTTPException(400, "媒体类型只支持 audio/image/video")

    content = await file.read()
    if not content:
        raise HTTPException(400, "文件为空")
    if len(content) > _MAX_MEDIA_SIZE:
        raise HTTPException(400, "文件过大，请控制在 80MB 内")

    ext = _safe_ext(file, media_type)
    rel_dir = Path("orders") / str(order_id)
    target_dir = _upload_root() / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d%H%M%S")
    uploader = uploader_id if uploader_id is not None else "guest"
    filename = f"order{order_id}_user{uploader}_{timestamp}_{uuid4().hex[:8]}{ext}"
    target_path = target_dir / filename
    target_path.write_bytes(content)

    media = _media_list(order)
    media.append({
        "type": media_type,
        "url": f"/uploads/{rel_dir.as_posix()}/{filename}",
        "name": name or file.filename or filename,
        "original_name": original_name or file.filename or filename,
        "uploader_id": uploader_id,
        "size": len(content),
        "duration": duration or 0,
        "content_type": file.content_type,
    })
    order.media_json = json.dumps(media, ensure_ascii=False)
    await db.commit()
    await db.refresh(order)
    return order


@router.patch("/{order_id}", response_model=OrderOut)
async def update_order(
    order_id: int, data: OrderUpdate, db: AsyncSession = Depends(get_db)
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    try:
        return await order_service.update_order(db, order, data)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ═══════════════════════════════════════════════════════════════
# 新增：状态流转 API
# ═══════════════════════════════════════════════════════════════

@router.post("/{order_id}/transition", response_model=OrderOut)
async def transition_order(
    order_id: int,
    data: OrderTransition,
    db: AsyncSession = Depends(get_db),
):
    """执行状态流转（customer 确认完成 / repairer 接单 / admin 改状态）"""
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    try:
        return await order_service.transition_status(
            db, order,
            to_status=data.to_status,
            operator_type=data.operator_type,
            operator_id=data.operator_id,
            remark=data.remark,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


# ═══════════════════════════════════════════════════════════════
# 新增：派单 API
# ═══════════════════════════════════════════════════════════════

@router.post("/{order_id}/auto-dispatch", response_model=OrderOut)
async def auto_dispatch_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
):
    """自动派单：区域优先匹配合适师傅"""
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    try:
        return await order_service.auto_dispatch(db, order)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{order_id}/store-accept", response_model=OrderOut)
async def store_accept_order(
    order_id: int,
    manager_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    try:
        return await order_service.store_accept(db, order, manager_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{order_id}/assign", response_model=OrderOut)
async def manual_assign_order(
    order_id: int,
    data: OrderAssign,
    db: AsyncSession = Depends(get_db),
):
    """管理员手动指派师傅"""
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    try:
        return await order_service.manual_assign(db, order, data.repairer_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{order_id}/self-service", response_model=OrderOut)
async def store_self_service(
    order_id: int,
    data: StoreSelfServiceRequest,
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    try:
        return await order_service.store_self_service(
            db, order, data.manager_id, data.skills
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{order_id}/service-bill", response_model=ServiceBillOut)
async def submit_service_bill(
    order_id: int,
    data: ServiceBillCreate,
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    try:
        return await bill_service.submit_bill(db, order, data)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{order_id}/service-bill/latest", response_model=ServiceBillOut)
async def get_latest_service_bill(
    order_id: int,
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, order_id)
    bill = await bill_service.get_latest_bill(db, order_id)
    if not order or not bill:
        raise HTTPException(404, "服务单不存在")
    return bill


@router.post("/{order_id}/service-bill/return", response_model=ServiceBillOut)
async def return_service_bill(
    order_id: int,
    data: ServiceBillReturn,
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, order_id)
    bill = await bill_service.get_latest_bill(db, order_id)
    if not order or not bill:
        raise HTTPException(404, "订单或服务单不存在")
    try:
        return await bill_service.return_bill(db, order, bill, data.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{order_id}/service-bill/confirm", response_model=ServiceBillOut)
async def confirm_service_bill(
    order_id: int,
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, order_id)
    bill = await bill_service.get_latest_bill(db, order_id)
    if not order or not bill:
        raise HTTPException(404, "订单或服务单不存在")
    try:
        return await bill_service.confirm_bill(db, order, bill)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{order_id}/rating", response_model=OrderOut)
async def rate_order(
    order_id: int,
    data: OrderRatingRequest,
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    return await order_service.rate_order(db, order, data.rating, data.remark)


@router.post("/{order_id}/store-review", response_model=OrderOut)
async def store_review_order(
    order_id: int,
    data: StoreReviewRequest,
    manager_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    try:
        return await order_service.store_review_complete(
            db,
            order,
            data.technician_wage_amount,
            manager_id,
            data.remark,
            data.wage_mode,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


# ═══════════════════════════════════════════════════════════════
# 新增：流转日志查询
# ═══════════════════════════════════════════════════════════════

@router.get("/{order_id}/logs", response_model=list[OrderLogOut])
async def get_order_logs(
    order_id: int,
    db: AsyncSession = Depends(get_db),
):
    """查询订单流转日志"""
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    return await order_service.get_order_logs(db, order_id)
