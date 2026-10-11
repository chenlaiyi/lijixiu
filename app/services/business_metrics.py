"""业务指标采集(2026-10-07 从 app/main.py 抽出)。

抽出原因:`/metrics`(Prometheus 抓取,走 nginx basic auth)
和后台概览页要的是**同一份口径**。后台改为走
`GET /api/v1/admin/metrics`(Bearer token),两个端点共用本模块。

如果放在 main.py 里,admin 路由 import main 会形成循环导入,所以独立成模块。

⚠️ 枚举列落库为**成员名**(大写),raw SQL 必须用同一口径。
早期代码写的是枚举值(小写),导致 `/metrics` 恒为 0、Prometheus 告警永不触发。
"""
from __future__ import annotations

from sqlalchemy import text

from ..models.alert_event import AlertSeverity
from ..models.order import OrderStatus
from ..models.reconciliation import ReconcileStatus

_COMPLETED = OrderStatus.COMPLETED.name
_PENDING_STATUSES = ",".join(
    f"'{member.name}'"
    for member in (
        OrderStatus.STORE_PENDING,
        OrderStatus.STORE_ACCEPTED,
        OrderStatus.DISPATCHED,
        OrderStatus.ASSIGNED,
    )
)
_RECON_MISMATCH = ReconcileStatus.MISMATCH.name
_SEV_CRITICAL = AlertSeverity.CRITICAL.name
_SEV_WARNING = AlertSeverity.WARNING.name


async def business_metrics(db) -> dict[str, int | float]:
    """采集业务指标。JSON / Prometheus / 后台概览三处共用同一份口径。"""
    return {
        "orders_total": (await db.execute(text("SELECT COUNT(*) FROM orders"))).scalar() or 0,
        "orders_completed": (
            await db.execute(
                text(f"SELECT COUNT(*) FROM orders WHERE status='{_COMPLETED}'")
            )
        ).scalar()
        or 0,
        "orders_pending": (
            await db.execute(
                text(f"SELECT COUNT(*) FROM orders WHERE status IN ({_PENDING_STATUSES})")
            )
        ).scalar()
        or 0,
        "wallets_total": (await db.execute(text("SELECT COUNT(*) FROM wallets"))).scalar() or 0,
        "total_balance": (
            await db.execute(text("SELECT COALESCE(SUM(available_balance), 0) FROM wallets"))
        ).scalar()
        or 0,
        "alerts_active": (
            await db.execute(text("SELECT COUNT(*) FROM alert_events WHERE resolved=0"))
        ).scalar()
        or 0,
        "alerts_critical": (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM alert_events "
                    f"WHERE resolved=0 AND severity='{_SEV_CRITICAL}'"
                )
            )
        ).scalar()
        or 0,
        "alerts_warning": (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM alert_events "
                    f"WHERE resolved=0 AND severity='{_SEV_WARNING}'"
                )
            )
        ).scalar()
        or 0,
        "last_recon_mismatch": (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM reconciliation_logs "
                    f"WHERE status='{_RECON_MISMATCH}' AND created_at = "
                    "(SELECT MAX(created_at) FROM reconciliation_logs)"
                )
            )
        ).scalar()
        or 0,
    }
