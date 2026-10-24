"""Personal referral codes and shareable mini-program QR codes."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user
from ..core.database import get_db
from ..models.user import User
from ..services import user as users
from ..services import wechat_pay
from ..services.wechat_pay import WeChatPayError

router = APIRouter(prefix="/api/v1/referrals", tags=["推荐"])


@router.get("/me")
async def my_referral(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    code = await users.ensure_referral_code(db, user)
    return {
        "code": code,
        "share_path": f"/pages/index/index?ref={code}",
        "qr_image_url": f"/api/v1/referrals/{code}/qrcode.png",
        "reward_ratio_percent": 1.0,
    }


@router.get("/{code}/qrcode.png")
async def referral_qrcode(code: str, db: AsyncSession = Depends(get_db)):
    owner = (
        await db.execute(
            select(User).where(
                User.referral_code == code,
                User.is_active.is_(True),
                User.deletion_scheduled_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not owner:
        raise HTTPException(404, "推荐码不存在或账号已停用")
    try:
        image = wechat_pay.get_mini_program_code(code, "pages/index/index")
    except (WeChatPayError, OSError) as exc:
        raise HTTPException(503, "推广二维码暂不可用") from exc
    return Response(image, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


class BindReferralRequest(BaseModel):
    code: str = Field(min_length=8, max_length=32)


@router.post("/bind")
async def bind_referral(data: BindReferralRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await users.bind_referrer(db, user, data.code)
    return {"bound": user.referrer_user_id is not None, "referrer_user_id": user.referrer_user_id}
