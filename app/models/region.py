"""Region model v2 - adds region manager (admin owner)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Region(Base):
    """Region with three levels: province / city / district."""

    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(100), comment="Region name (e.g. 福建省 / 厦门市 / 思明区)"
    )
    level: Mapped[int] = mapped_column(
        Integer, comment="1 = province, 2 = city, 3 = district"
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id"), nullable=True, comment="Parent region id"
    )
    # --- 2026-08-09: added region manager (admin user) ---
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, comment="Region manager (admin) user id"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
