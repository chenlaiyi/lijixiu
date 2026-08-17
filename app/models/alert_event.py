"""Alert event model."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AlertType(str, enum.Enum):
    PAYMENT_FAILED = "payment_failed"
    WALLET_INCONSISTENCY = "wallet_inconsistency"
    PROFIT_ERROR = "profit_error"
    RECONCILE_MISMATCH = "reconcile_mismatch"


class AlertSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertEvent(Base):
    """Monitoring alert event - all anomalies are queryable here."""

    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[AlertType] = mapped_column(
        Enum(AlertType, name="alerttype"),
        index=True,
        comment="Alert type: payment_failed / wallet_inconsistency / profit_error / reconcile_mismatch",
    )
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity, name="alertseverity"),
        default=AlertSeverity.WARNING,
        comment="Severity: info / warning / critical",
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, comment="Related user id"
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id"), nullable=True, comment="Related order id"
    )
    amount: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Amount involved"
    )
    message: Mapped[str] = mapped_column(Text, comment="Alert short message")
    detail: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Full detail (stack / context JSON)"
    )
    resolved: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="Whether the alert has been resolved"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
