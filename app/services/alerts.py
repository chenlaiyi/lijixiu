"""告警服务 — 监控异常事件"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.alert_event import AlertEvent, AlertSeverity, AlertType


async def create_alert(
    db: AsyncSession,
    alert_type: AlertType,
    message: str,
    severity: AlertSeverity = AlertSeverity.WARNING,
    user_id: int | None = None,
    order_id: int | None = None,
    amount: float | None = None,
    detail: str | None = None,
) -> AlertEvent:
    event = AlertEvent(
        type=alert_type,
        severity=severity,
        user_id=user_id,
        order_id=order_id,
        amount=amount,
        message=message,
        detail=detail,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def list_alerts(
    db: AsyncSession,
    alert_type: str | None = None,
    resolved: bool | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[AlertEvent]:
    stmt = select(AlertEvent)
    if alert_type:
        stmt = stmt.where(AlertEvent.type == alert_type)
    if resolved is not None:
        stmt = stmt.where(AlertEvent.resolved == resolved)
    stmt = stmt.order_by(AlertEvent.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def resolve_alert(db: AsyncSession, alert_id: int) -> AlertEvent | None:
    event = await db.get(AlertEvent, alert_id)
    if event:
        event.resolved = True
        await db.commit()
        await db.refresh(event)
    return event
