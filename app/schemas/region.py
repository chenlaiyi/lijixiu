"""区域 Schema v2"""

from datetime import datetime

from pydantic import BaseModel, Field


class RegionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    level: int = Field(default=1, ge=1, le=3)
    parent_id: int | None = None
    manager_id: int | None = None


class RegionUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    manager_id: int | None = None


class RegionOut(BaseModel):
    id: int
    name: str
    level: int
    parent_id: int | None
    manager_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
