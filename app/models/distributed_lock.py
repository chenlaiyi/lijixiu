"""Distributed lock model (SQLite implementation)."""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DistributedLockRecord(Base):
    """Single-row distributed lock entry, keyed by string lock key."""

    __tablename__ = "distributed_locks"

    key: Mapped[str] = mapped_column(
        String(200), primary_key=True, comment="Lock key (string)"
    )
    owner: Mapped[str] = mapped_column(
        String(50), comment="Lock owner id (caller identifier)"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), comment="Lock expiry timestamp"
    )
