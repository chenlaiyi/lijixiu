"""Idempotency key model - prevents duplicate wallet operations."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class IdempotencyStatus(str, enum.Enum):
    PROCESSING = "processing"
    DONE = "done"


class IdempotencyKey(Base):
    """All wallet-related operations must first acquire/check an idempotency key.

    Once the operation is committed, status -> DONE and `result` holds the cached
    JSON body for replay.
    """

    __tablename__ = "idempotency_keys"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(
        String(200),
        unique=True,
        index=True,
        comment="Unique key in the form of action:resource_id",
    )
    status: Mapped[IdempotencyStatus] = mapped_column(
        Enum(IdempotencyStatus, name="idempotencystatus"),
        default=IdempotencyStatus.PROCESSING,
        comment="processing | done",
    )
    result: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Cached JSON result, written when status=DONE"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


def make_key(action: str, resource_id: int | str) -> str:
    """Build a stable idempotency key for a given action/resource pair."""
    return f"{action}:{resource_id}"


# Standard action names for wallet-critical flows.
KEY_ORDER_COMPLETE = "order_complete"          # + order_id
KEY_PROFIT_SETTLE = "profit_settle"            # + order_id
KEY_WITHDRAW = "withdraw"                      # + withdrawal_id
KEY_WITHDRAW_REVIEW = "withdraw_review"        # + withdrawal_id
