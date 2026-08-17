"""用户路由"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..schemas.user import UserCreate, UserOut, UserUpdate
from ..services import user as user_service

router = APIRouter(prefix="/api/v1/users", tags=["用户"])


@router.post("", response_model=UserOut, status_code=201)
async def create_user(data: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await user_service.get_user_by_phone(db, data.phone)
    if existing:
        raise HTTPException(400, "手机号已注册")
    return await user_service.create_user(db, data)


@router.get("", response_model=list[UserOut])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    role: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await user_service.list_users(db, skip, limit, role)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await user_service.get_user(db, user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int, data: UserUpdate, db: AsyncSession = Depends(get_db)
):
    user = await user_service.get_user(db, user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    return await user_service.update_user(db, user, data)
