"""Repairer model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Repairer(Base):
    """A repairer maps 1:1 to a User whose role is 'repairer'."""

    __tablename__ = "repairers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), unique=True, comment="Linked user id"
    )
    skills: Mapped[str] = mapped_column(
        String(500), comment="Skill tags, comma-separated"
    )
    rating: Mapped[float] = mapped_column(
        Float, default=5.0, comment="Customer rating 1.0-5.0"
    )
    order_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="Completed order count"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="offline",
        comment="online | offline | busy",
    )
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id"), nullable=True, comment="Service region id"
    )
    id_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="Real-name ID verified"
    )
    id_card: Mapped[str | None] = mapped_column(
        String(18), nullable=True, comment="ID card number (encrypted in production)"
    )
    intro: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Self introduction"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
