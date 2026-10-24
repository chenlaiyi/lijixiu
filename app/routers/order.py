"""订单路由 v2"""

import json
import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user, is_staff, require_staff
from ..core.config import settings
from ..core.database import get_db
from ..models.user import User, UserRole
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
from ..services import repairer as repairer_service
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


async def _own_repairer_id(db: AsyncSession, user: User) -> int | None:
    """当前用户对应的「师傅档案 id」。

    2026-10-06:小程序师傅端传的是 `repairer.id`(师傅档案 id),不是 `user.id`;
    两者只有恰好落在同一批种子数据里时才相等。之前按 user.id 比对,会把师傅端
    工单列表全部判成 403。这里做一次归属校验,把档案 id 也认作「自己」。
    """
    repairer = await repairer_service.get_repairer_by_user(db, user.id)
    return repairer.id if repairer else None


async def _require_order_visible(db: AsyncSession, order, user: User) -> None:
    """2026-10-05:订单只能被「本人/指派师傅/平台内部角色」查看与操作。

    订单里含客户姓名、电话、地址等个人信息,之前 /api/v1/orders 全裸奔。
    """
    if is_staff(user):
        return
    if order.customer_id == user.id:
        return
    if order.assigned_repairer_id == user.id or order.repairer_id == user.id:
        return
    own = await _own_repairer_id(db, user)
    if own is not None and (
        order.assigned_repairer_id == own or order.repairer_id == own
    ):
        return
    raise HTTPException(403, "not your order")


@router.post("", response_model=OrderOut, status_code=201)
async def create_order(
    data: OrderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05:必须登录
):
    # 客户只能给自己下单;内部角色可代客下单
    if not is_staff(user) and data.customer_id != user.id:
        raise HTTPException(403, "cannot create order for another customer")
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
    user: User = Depends(get_current_user),  # 2026-10-05:必须登录
):
    # 非内部角色强制收口到「自己的订单」,避免越权枚举他人订单(PII)
    if not is_staff(user):
        own_repairer_id = await _own_repairer_id(db, user)
        allowed = {user.id}
        if own_repairer_id is not None:
            allowed.add(own_repairer_id)
        if customer_id is not None and customer_id != user.id:
            raise HTTPException(403, "not your order")
        if assigned_repairer_id is not None and assigned_repairer_id not in allowed:
            raise HTTPException(403, "not your order")
        if repairer_id is not None and repairer_id not in allowed:
            raise HTTPException(403, "not your order")
        if user.role == UserRole.REPAIRER:
            # 师傅侧不传参数时会扫全表(等于泄露全部订单),这里兜底为「自己名下」
            return await order_service.list_orders(
                db, skip, limit, None, own_repairer_id or user.id, None,
                status, region_id, store_id, is_proxy_order,
            )
        return await order_service.list_orders(
            db, skip, limit, user.id, None, None,
            status, region_id, store_id, is_proxy_order,
        )
    return await order_service.list_orders(
        db, skip, limit, customer_id, repairer_id,
        assigned_repairer_id, status, region_id, store_id, is_proxy_order,
    )


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    await _require_order_visible(db, order, user)
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
    user: User = Depends(get_current_user),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    await _require_order_visible(db, order, user)
    # 素材归属以登录用户为准,忽略客户端传入的 uploader_id
    uploader_id = user.id
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
    order_id: int,
    data: OrderUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    await _require_order_visible(db, order, user)
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
    user: User = Depends(get_current_user),
):
    """执行状态流转（customer 确认完成 / repairer 接单 / admin 改状态）"""
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    await _require_order_visible(db, order, user)
    # 操作者身份以登录用户为准,禁止伪造 operator_id
    operator_type = data.operator_type
    operator_id = user.id
    if is_staff(user):
        operator_type = "admin"
    try:
        return await order_service.transition_status(
            db, order,
            to_status=data.to_status,
            operator_type=operator_type,
            operator_id=operator_id,
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
    _staff: User = Depends(require_staff),
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
    _staff: User = Depends(require_staff),
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
    _staff: User = Depends(require_staff),
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
    _staff: User = Depends(require_staff),
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
    user: User = Depends(get_current_user),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    await _require_order_visible(db, order, user)
    own_repairer_id = await _own_repairer_id(db, user)
    if own_repairer_id != data.repairer_id:
        raise HTTPException(403, "仅服务师傅本人可以提交服务单")
    try:
        return await bill_service.submit_bill(db, order, data)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{order_id}/service-bill/latest", response_model=ServiceBillOut)
async def get_latest_service_bill(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "服务单不存在")
    # 2026-10-06:先校验归属再查单据,避免用 404/200 的差异探测他人订单是否有服务单
    await _require_order_visible(db, order, user)
    bill = await bill_service.get_latest_bill(db, order_id)
    if not bill:
        raise HTTPException(404, "服务单不存在")
    return bill


@router.post("/{order_id}/service-bill/return", response_model=ServiceBillOut)
async def return_service_bill(
    order_id: int,
    data: ServiceBillReturn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单或服务单不存在")
    await _require_order_visible(db, order, user)
    bill = await bill_service.get_latest_bill(db, order_id)
    if not bill:
        raise HTTPException(404, "订单或服务单不存在")
    try:
        return await bill_service.return_bill(db, order, bill, data.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{order_id}/service-bill/confirm", response_model=ServiceBillOut)
async def confirm_service_bill(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单或服务单不存在")
    await _require_order_visible(db, order, user)
    bill = await bill_service.get_latest_bill(db, order_id)
    if not bill:
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
    user: User = Depends(get_current_user),
):
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    await _require_order_visible(db, order, user)
    return await order_service.rate_order(db, order, data.rating, data.remark)


@router.post("/{order_id}/store-review", response_model=OrderOut)
async def store_review_order(
    order_id: int,
    data: StoreReviewRequest,
    manager_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
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
    user: User = Depends(get_current_user),
):
    """查询订单流转日志"""
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(404, "订单不存在")
    await _require_order_visible(db, order, user)
    return await order_service.get_order_logs(db, order_id)
