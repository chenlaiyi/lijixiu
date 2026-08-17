"""Support center schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from ..models.support_ticket import SupportTicketStatus


class SupportTicketCreate(BaseModel):
    store_id: int
    user_id: int
    order_id: int | None = None
    category: str = "general"
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1)


class SupportReplyCreate(BaseModel):
    user_id: int
    content: str = Field(min_length=1)
    close: bool = False


class SupportTicketOut(BaseModel):
    id: int
    store_id: int
    user_id: int
    order_id: int | None
    category: str
    title: str
    content: str
    status: SupportTicketStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
