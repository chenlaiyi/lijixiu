"""师傅路由"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user, is_staff, require_staff, require_staff_or_self
from ..core.database import get_db
from ..models.user import User, UserRole
from ..schemas.repairer import RepairerCreate, RepairerOut, RepairerUpdate
from ..services import repairer as repairer_service
from ..services import user as user_service

router = APIRouter(prefix="/api/v1/repairers", tags=["师傅"])


@router.post("", response_model=RepairerOut, status_code=201)
async def create_repairer(
    data: RepairerCreate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),  # 2026-10-05:建师傅档案仅内部角色
):
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
    user: User = Depends(get_current_user),  # 2026-10-05:师傅名录仅登录用户
):
    return await repairer_service.list_repairers(db, skip, limit, region_id, status)


@router.get("/{repairer_id}", response_model=RepairerOut)
async def get_repairer(
    repairer_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = await repairer_service.get_repairer(db, repairer_id)
    if not r:
        raise HTTPException(404, "师傅不存在")
    # 本人 / 内部角色可看完整档案,其他登录用户只允许看列表级信息
    if not is_staff(user) and r.user_id != user.id:
        raise HTTPException(403, "not your profile")
    return r


@router.patch("/{repairer_id}", response_model=RepairerOut)
async def update_repairer(
    repairer_id: int,
    data: RepairerUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = await repairer_service.get_repairer(db, repairer_id)
    if not r:
        raise HTTPException(404, "师傅不存在")
    require_staff_or_self(r.user_id, user)
    return await repairer_service.update_repairer(db, r, data)
