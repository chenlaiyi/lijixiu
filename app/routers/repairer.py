"""师傅路由"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..models.user import UserRole
from ..schemas.repairer import RepairerCreate, RepairerOut, RepairerUpdate
from ..services import repairer as repairer_service
from ..services import user as user_service

router = APIRouter(prefix="/api/v1/repairers", tags=["师傅"])


@router.post("", response_model=RepairerOut, status_code=201)
async def create_repairer(data: RepairerCreate, db: AsyncSession = Depends(get_db)):
    user = await user_service.get_user(db, data.user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    if user.role not in (UserRole.REPAIRER, UserRole.ADMIN):
        raise HTTPException(400, "该用户不能创建服务档案")
    existing = await repairer_service.get_repairer_by_user(db, data.user_id)
    if existing:
        raise HTTPException(400, "该用户已是师傅")
    return await repairer_service.create_repairer(db, data)


@router.get("", response_model=list[RepairerOut])
async def list_repairers(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    region_id: int | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await repairer_service.list_repairers(db, skip, limit, region_id, status)


@router.get("/{repairer_id}", response_model=RepairerOut)
async def get_repairer(repairer_id: int, db: AsyncSession = Depends(get_db)):
    r = await repairer_service.get_repairer(db, repairer_id)
    if not r:
        raise HTTPException(404, "师傅不存在")
    return r


@router.patch("/{repairer_id}", response_model=RepairerOut)
async def update_repairer(
    repairer_id: int, data: RepairerUpdate, db: AsyncSession = Depends(get_db)
):
    r = await repairer_service.get_repairer(db, repairer_id)
    if not r:
        raise HTTPException(404, "师傅不存在")
    return await repairer_service.update_repairer(db, r, data)
