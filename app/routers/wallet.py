"""Wallet routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user, is_staff, require_admin, require_self_or_admin
from ..core.database import get_db
from ..core.logging import get_audit_logger, get_security_logger
from ..models.user import User
from ..schemas.wallet import (
    LedgerOut,
    WalletOut,
    WithdrawalCreate,
    WithdrawalOut,
    WithdrawalReview,
)
from ..services import safety, wallet as wallet_service
from ..services import wechat_pay
from ..services.wechat_pay import WeChatPayError

router = APIRouter(prefix="/api/v1/wallet", tags=["wallet"])

audit_log = get_audit_logger()
security_log = get_security_logger()


@router.get("/balance/{user_id}", response_model=WalletOut)
async def get_balance(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-08-09 加鉴权
):
    require_self_or_admin(user_id, user)
    return await wallet_service.get_or_create_wallet(db, user_id)


@router.get("/ledger/{user_id}", response_model=list[LedgerOut])
async def get_ledger(
    user_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    type: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-08-09 加鉴权
):
    require_self_or_admin(user_id, user)
    return await wallet_service.get_ledger(db, user_id, skip, limit, type)


@router.post("/withdraw/{user_id}", response_model=WithdrawalOut, status_code=201)
async def request_withdraw(
    request: Request,
    user_id: int,
    data: WithdrawalCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-08-09 加鉴权
):
    require_self_or_admin(user_id, user)
    try:
        withdrawal = await wallet_service.request_withdrawal(db, user_id, data.amount, data.remark)
    except (ValueError, safety.SafetyError) as e:
        raise HTTPException(400, str(e))
    audit_log.info(
        "提现申请",
        extra={
            "request_id": getattr(request.state, "request_id", "-"),
            "trace_id": getattr(request.state, "trace_id", "-"),
            "actor_user_id": user.id,
            "user_id": user.id,
            "withdrawal_id": withdrawal.id,
            "amount": withdrawal.amount,
            "remark": withdrawal.remark,
        },
    )
    return withdrawal


@router.post("/withdraw/{withdrawal_id}/review", response_model=WithdrawalOut)
async def review_withdraw(
    request: Request,
    withdrawal_id: int,
    data: WithdrawalReview,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),  # 2026-08-09 仅管理员
):
    try:
        withdrawal = await wallet_service.review_withdrawal(
            db,
            withdrawal_id,
            data.action,
            data.remark,
            data.payout_method,
        )
    except (ValueError, safety.SafetyError, WeChatPayError) as e:
        raise HTTPException(400, str(e))
    audit_log.info(
        "提现审核",
        extra={
            "request_id": getattr(request.state, "request_id", "-"),
            "trace_id": getattr(request.state, "trace_id", "-"),
            "actor_user_id": admin.id,
            "actor_business_role": admin.business_role,
            "withdrawal_id": withdrawal.id,
            "user_id": withdrawal.user_id,
            "amount": withdrawal.amount,
            "action": data.action,
            "new_status": withdrawal.status.value,
            "remark": data.remark,
        },
    )
    return withdrawal


@router.post("/withdraw/{withdrawal_id}/wechat-sync", response_model=WithdrawalOut)
async def sync_wechat_withdrawal(
    withdrawal_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),  # 2026-08-09 仅管理员
):
    try:
        return await wallet_service.sync_wechat_withdrawal(db, withdrawal_id)
    except (ValueError, safety.SafetyError, WeChatPayError) as e:
        raise HTTPException(400, str(e))


@router.post("/wechat/transfer-notify")
async def wechat_transfer_notify(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """微信支付回调,无需 token(由微信签名验证)。"""
    body = (await request.body()).decode("utf-8")
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        await wallet_service.handle_wechat_transfer_notification(db, headers, body)
        return {"code": "SUCCESS", "message": "success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"code": "FAIL", "message": str(e)})


@router.get("/wechat-transfer/config-status")
async def wechat_transfer_config_status(
    _admin: User = Depends(require_admin),  # 2026-08-09 仅管理员
):
    status = wechat_pay.config_status()
    return {
        "ready": status["transfer_ready"],
        "auto_enabled": status["transfer_auto_enabled"],
        "scene_id_configured": status["transfer_scene_id_configured"],
        "app_secret_configured": status["app_secret_configured"],
        "issues": status["transfer_issues"],
    }


@router.get("/withdrawals", response_model=list[WithdrawalOut])
async def list_withdrawals(
    user_id: int | None = None,
    status: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """提现记录列表。

    2026-10-07:原来是 `require_admin`。但小程序「收益」页要展示
    **自己的**提现记录(`/api/v1/wallet/withdrawals?user_id=<自己>`),
    收成 admin-only 后该页只能拿到空列表 —— 提审演示时审核员看不到刚提交的申请。
    这里改成与 `/balance/{user_id}`、`/ledger/{user_id}` 一致的收敛方式:
    本人只能查自己,平台内部角色可查任意/全部。
    """
    if not is_staff(user):
        if user_id is not None and user_id != user.id:
            raise HTTPException(403, "not your withdrawal")
        user_id = user.id
    return await wallet_service.list_withdrawals(db, user_id, status, skip, limit)
