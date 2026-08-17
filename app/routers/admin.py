"""管理员路由 v2 — 对账 + 告警 + 监控"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import require_admin
from ..core.database import get_db, engine
from ..core.logging import get_audit_logger, get_security_logger
from ..models.alert_event import AlertEvent, AlertType
from ..models.user import User
from ..services import alerts, safety

audit_log = get_audit_logger()
security_log = get_security_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["管理"])


async def _existing_reconcile_alert(db: AsyncSession, wallet_id: int) -> AlertEvent | None:
    """每个钱包最多一条未解决的 reconcile_mismatch 告警(2026-08-09 修复去重)。"""
    r = await db.execute(
        select(AlertEvent)
        .where(
            AlertEvent.type == AlertType.RECONCILE_MISMATCH,
            AlertEvent.resolved == False,  # noqa: E712
            AlertEvent.message.like(f"%钱包#{wallet_id}%"),
        )
        .order_by(AlertEvent.created_at.desc())
        .limit(1)
    )
    return r.scalar_one_or_none()


# ═══════════════════ 对账 ═══════════════════

@router.post("/reconcile/run")
async def run_reconciliation(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),  # 2026-08-09 加鉴权
):
    audit_log.info(
        "对账触发",
        extra={
            "request_id": getattr(request.state, "request_id", "-"),
            "trace_id": getattr(request.state, "trace_id", "-"),
            "actor_user_id": admin.id,
            "actor_business_role": admin.business_role,
        },
    )
    logs = await safety.run_reconciliation(db)
    ok = sum(1 for l in logs if l.status == "ok")
    mismatch = sum(1 for l in logs if l.status == "mismatch")

    # 差异写入告警(去重:每钱包最多一条未解决告警)
    created = 0
    skipped = 0
    if mismatch > 0:
        for l in logs:
            if l.status == "mismatch":
                existing = await _existing_reconcile_alert(db, l.wallet_id)
                if existing:
                    # 已存在未解决告警,更新 detail 和 amount(让最新对账结果覆盖)
                    existing.amount = l.difference
                    existing.detail = l.detail
                    skipped += 1
                else:
                    await alerts.create_alert(
                        db,
                        AlertType.RECONCILE_MISMATCH,
                        f"钱包#{l.wallet_id} 对账差异: {l.difference}",
                        severity="critical",
                        user_id=l.user_id,
                        amount=l.difference,
                        detail=l.detail,
                    )
                    created += 1

    return {
        "total_wallets": len(logs),
        "ok": ok, "mismatch": mismatch,
        "alerts_created": created,
        "alerts_updated": skipped,
        "details": [
            {"wallet_id": l.wallet_id, "user_id": l.user_id,
             "status": l.status, "difference": l.difference}
            for l in logs if l.status == "mismatch"
        ],
    }


@router.get("/reconcile/logs")
async def get_reconciliation_logs(
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),  # 2026-08-09 加鉴权
):
    logs = await safety.get_last_reconciliation(db, limit)
    return [
        {"id": l.id, "wallet_id": l.wallet_id, "user_id": l.user_id,
         "expected_balance": l.expected_balance, "actual_balance": l.actual_balance,
         "difference": l.difference, "status": l.status,
         "detail": l.detail, "created_at": l.created_at.isoformat()}
        for l in logs
    ]


# ═══════════════════ 告警 ═══════════════════

@router.get("/alerts")
async def get_alerts(
    type: str | None = None,
    resolved: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),  # 2026-08-09 加鉴权
):
    items = await alerts.list_alerts(db, type, resolved, skip, limit)
    return [
        {"id": a.id, "type": a.type, "severity": a.severity,
         "user_id": a.user_id, "order_id": a.order_id,
         "amount": a.amount, "message": a.message,
         "detail": a.detail, "resolved": a.resolved,
         "created_at": a.created_at.isoformat()}
        for a in items
    ]


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),  # 2026-08-09 加鉴权
):
    a = await alerts.resolve_alert(db, alert_id)
    if not a:
        return {"error": "not found"}
    return {"id": a.id, "resolved": a.resolved}


# ═══════════════════ 对账修复(2026-08-09 P0 收尾)═══════════════════

from pydantic import BaseModel  # noqa: E402


class WalletAdjustRequest(BaseModel):
    user_id: int
    amount: float  # 正数:ledger_sum += amount,负数:ledger_sum -= amount
    remark: str | None = None


@router.post("/wallet/adjust")
async def admin_wallet_adjust(
    request: Request,
    data: WalletAdjustRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),  # 仅管理员
):
    """对账差异修复:写一条 MANUAL_ADJUST ledger 让 ledger_sum == wallet total。

    不修改 wallet 字段(因为 wallet 是真值,差异源自历史 ledger 缺失或错误)。
    跑完后调 /admin/reconcile/run 确认 mismatch=0。
    """
    from ..services import safety as safety_svc
    wallet, ledger = await safety_svc.safe_reconcile_adjust(
        db,
        user_id=data.user_id,
        amount=data.amount,
        remark=data.remark or "admin 对账修复",
        operator_user_id=admin.id,
    )
    # 审计:对账修复是高风险操作,必留痕
    audit_log.info(
        "对账修复 adjust",
        extra={
            "request_id": getattr(request.state, "request_id", "-"),
            "trace_id": getattr(request.state, "trace_id", "-"),
            "actor_user_id": admin.id,
            "actor_business_role": admin.business_role,
            "target_user_id": wallet.user_id,
            "wallet_id": wallet.id,
            "amount": ledger.amount,
            "ledger_id": ledger.id,
        },
    )
    return {
        "ledger_id": ledger.id,
        "wallet_id": wallet.id,
        "user_id": wallet.user_id,
        "amount": ledger.amount,
        "balance_after": ledger.balance_after,
        "available_balance": wallet.available_balance,
        "frozen_balance": wallet.frozen_balance,
        "operator_user_id": admin.id,
        "remark": ledger.remark,
    }


# ═══════════════════ 微信支付诊断(2026-08-09 P1)═══════════════════


@router.get("/wechat-pay/diagnostics")
async def admin_wechat_pay_diagnostics(
    admin: User = Depends(require_admin),
):
    """微信支付运行时诊断:配置 + 平台证书下载状态。

    如果 `consecutive_failures >= 3` 或 `cached_count == 0` 且 `cooldown_active`:
        - 说明平台证书下载失败
        - 支付回调会 100% 验签失败
        - 立即操作:打 95017 OR 配 WECHAT_PAY_PLATFORM_CERT_PATH
    """
    from ..services import wechat_pay as wp
    return {
        "config": wp.config_status(),
        "platform_cert": wp.platform_cert_status(),
    }
