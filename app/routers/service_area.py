"""Service-area address-library and coverage assignment routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user, require_admin
from ..core.database import get_db
from ..models.user import User
from ..schemas.service_area import (
    AssignmentLogOut,
    BulkAssignmentRequest,
    BulkAssignmentResult,
    BulkClearRequest,
    ServiceAreaListResponse,
)
from ..services import service_area as service

router = APIRouter(prefix="/api/v1/service-areas", tags=["服务区域地址库"])


@router.post("/sync-xiamen")
async def sync_xiamen(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),  # 2026-10-05
):
    return await service.sync_xiamen_service_areas(db)


@router.get("/filters")
async def filters(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),  # 2026-10-05
):
    return await service.service_area_filters(db)


@router.get("", response_model=ServiceAreaListResponse)
async def list_areas(
    district: str | None = None,
    street: str | None = None,
    q: str | None = None,
    assignment_status: str | None = Query(
        default=None, pattern="^(assigned|unassigned|conflict)$"
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),  # 2026-10-05
):
    return await service.list_service_areas(
        db, district, street, q, assignment_status, skip, limit
    )


@router.post("/assignments/bulk", response_model=BulkAssignmentResult)
async def bulk_assign(
    data: BulkAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),  # 2026-10-05
):
    try:
        return await service.bulk_assign_service_areas(db, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/assignments/bulk-clear", response_model=BulkAssignmentResult)
async def bulk_clear(
    data: BulkClearRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),  # 2026-10-05
):
    return await service.bulk_clear_service_areas(db, data)


@router.get("/assignment-logs", response_model=list[AssignmentLogOut])
async def logs(
    service_area_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),  # 2026-10-05:分配审计日志仅管理员
):
    return await service.assignment_logs(db, service_area_id, limit)
