"""Schemas for Xiamen address-library coverage management."""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ServiceAreaItem(BaseModel):
    id: int
    code: str
    province: str
    city: str
    district: str
    street: str
    name: str
    area_type: str
    active: bool
    assignment_id: int | None = None
    primary_store_id: int | None = None
    primary_store_name: str | None = None
    backup_store_id: int | None = None
    backup_store_name: str | None = None
    manager_id: int | None = None
    manager_name: str | None = None
    assignment_status: str
    effective_from: datetime | None = None
    remark: str | None = None


class ServiceAreaListResponse(BaseModel):
    items: list[ServiceAreaItem]
    total: int
    skip: int
    limit: int
    assigned_count: int
    unassigned_count: int
    conflict_count: int
    source_name: str
    source_url: str
    source_published_at: str


class BulkAssignmentRequest(BaseModel):
    service_area_ids: list[int] = Field(min_length=1, max_length=1000)
    primary_store_id: int | None = None
    backup_store_id: int | None = None
    manager_id: int | None = None
    conflict_mode: str = Field(default="skip", pattern="^(skip|fill_empty|replace)$")
    effective_from: datetime | None = None
    remark: str | None = Field(default=None, max_length=500)
    operator_user_id: int | None = None
    dry_run: bool = False

    @model_validator(mode="after")
    def validate_assignment(self):
        if not any((self.primary_store_id, self.backup_store_id, self.manager_id)):
            raise ValueError("至少选择主服务门店、备用门店或负责人中的一项")
        if self.primary_store_id and self.primary_store_id == self.backup_store_id:
            raise ValueError("主服务门店和备用门店不能相同")
        self.service_area_ids = list(dict.fromkeys(self.service_area_ids))
        return self


class BulkClearRequest(BaseModel):
    service_area_ids: list[int] = Field(min_length=1, max_length=1000)
    operator_user_id: int | None = None
    remark: str | None = Field(default=None, max_length=500)
    dry_run: bool = False


class BulkAssignmentResult(BaseModel):
    selected: int
    created: int = 0
    updated: int = 0
    skipped: int = 0
    unchanged: int = 0
    conflicts: int = 0
    cleared: int = 0
    missing: int = 0
    conflict_samples: list[str] = Field(default_factory=list)
    dry_run: bool


class AssignmentLogOut(BaseModel):
    id: int
    service_area_id: int
    area_name: str
    action: str
    before_json: str | None
    after_json: str | None
    operator_user_id: int | None
    created_at: datetime
