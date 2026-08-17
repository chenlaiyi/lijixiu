"""师傅 Schema"""

from datetime import datetime

from pydantic import BaseModel, Field


class RepairerCreate(BaseModel):
    user_id: int
    skills: str = Field(examples=["水电,家电维修"])
    region_id: int | None = None
    intro: str | None = None


class RepairerUpdate(BaseModel):
    skills: str | None = None
    status: str | None = None
    region_id: int | None = None
    intro: str | None = None


class RepairerOut(BaseModel):
    id: int
    user_id: int
    skills: str
    rating: float
    order_count: int
    status: str
    region_id: int | None
    id_verified: bool
    intro: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
