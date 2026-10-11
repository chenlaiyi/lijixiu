"""Payment order model."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, enum_column


class PayStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"


class PayProvider(str, enum.Enum):
    MOCK = "mock"
    WECHAT = "wechat"
    ALIPAY = "alipay"


class PayOrder(Base):
    """A third-party payment attempt for one business order."""

    __tablename__ = "pay_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[float] = mapped_column(Float)
    status: Mapped[PayStatus] = mapped_column(
        enum_column(PayStatus), default=PayStatus.PENDING
    )
    provider: Mapped[PayProvider] = mapped_column(
        enum_column(PayProvider), default=PayProvider.WECHAT
    )
    transaction_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    out_trade_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    prepay_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payer_openid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notify_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
