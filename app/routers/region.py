"""区域路由 v2"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..schemas.region import RegionCreate, RegionOut, RegionUpdate
from ..services import region as region_service

router = APIRouter(prefix="/api/v1/regions", tags=["区域管理"])


@router.post("", response_model=RegionOut, status_code=201)
async def create_region(data: RegionCreate, db: AsyncSession = Depends(get_db)):
    if data.parent_id:
        parent = await region_service.get_region(db, data.parent_id)
        if not parent:
            raise HTTPException(404, "上级区域不存在")
    return await region_service.create_region(db, data)


@router.get("", response_model=list[RegionOut])
async def list_regions(
    parent_id: int | None = None,
    level: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await region_service.list_regions(db, parent_id, level)


@router.get("/tree", response_model=list[dict])
async def region_tree(db: AsyncSession = Depends(get_db)):
    """获取省→市→区的树形结构"""
    return await region_service.get_region_tree(db)


@router.get("/{region_id}", response_model=RegionOut)
async def get_region(region_id: int, db: AsyncSession = Depends(get_db)):
    r = await region_service.get_region(db, region_id)
    if not r:
        raise HTTPException(404, "区域不存在")
    return r


@router.patch("/{region_id}", response_model=RegionOut)
async def update_region(
    region_id: int,
    data: RegionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """修改区域（设置负责人等）"""
    r = await region_service.get_region(db, region_id)
    if not r:
        raise HTTPException(404, "区域不存在")
    return await region_service.update_region(db, r, data)
