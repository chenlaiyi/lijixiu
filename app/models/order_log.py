"""Order state-transition log model."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class OperatorType(str, enum.Enum):
    CUSTOMER = "customer"      # customer operation
    REPAIRER = "repairer"      # repairer operation
    ADMIN = "admin"            # admin operation
    SYSTEM = "system"          # automated (e.g. timeout / status sweep)


class OrderLog(Base):
    """Records every order state transition for audit."""

    __tablename__ = "order_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"), index=True, comment="Order id"
    )
    from_status: Mapped[str] = mapped_column(
        String(20), comment="Status before the change"
    )
    to_status: Mapped[str] = mapped_column(
        String(20), comment="Status after the change"
    )
    operator_type: Mapped[OperatorType] = mapped_column(
        Enum(OperatorType, name="operatortype"),
        comment="customer | repairer | admin | system",
    )
    operator_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True,
        comment="Operator user id (customer / repairer / admin)",
    )
    remark: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Free-form remark"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
