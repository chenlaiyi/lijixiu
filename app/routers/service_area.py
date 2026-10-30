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
        return await service.bulk_assign_service_areas(db, data.model_copy(update={"operator_user_id": _admin.id}))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/assignments/bulk-clear", response_model=BulkAssignmentResult)
async def bulk_clear(
    data: BulkClearRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),  # 2026-10-05
):
    return await service.bulk_clear_service_areas(db, data.model_copy(update={"operator_user_id": _admin.id}))


@router.get("/assignment-logs", response_model=list[AssignmentLogOut])
async def logs(
    service_area_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),  # 2026-10-05:分配审计日志仅管理员
):
    return await service.assignment_logs(db, service_area_id, limit)


@router.get("/customer-options")
async def customer_options(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await service.customer_options(db)


@router.get("/public-options")
async def public_options(db: AsyncSession = Depends(get_db)):
    """Public service coverage only; excludes order-derived addresses and operator data."""
    areas = await service.customer_options(db, include_order_estates=False)
    fields = {"id", "service_area_id", "name", "city", "district", "street", "estates"}
    return [{key: value for key, value in area.items() if key in fields} for area in areas]


@router.get("/address-catalog")
async def address_catalog(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from ..models.store import StoreAddress
    areas = await service.customer_options(db, include_order_estates=False)
    rows = (await db.execute(select(StoreAddress).where(StoreAddress.enabled == True,
        StoreAddress.catalog_published == True))).scalars().all()
    fields = {"id", "service_area_id", "name", "city", "district", "street", "estates"}
    result = []
    for area in areas:
        item = {key: value for key, value in area.items() if key in fields}
        item["addresses"] = [dict(id=row.id, estate=row.estate, building=row.building,
            unit=row.unit, room=row.room, door_number=row.door_number or "", aliases=row.aliases or "")
            for row in rows if row.service_area_id == area["id"]]
        result.append(item)
    return result
