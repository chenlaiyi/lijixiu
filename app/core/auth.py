"""统一鉴权依赖(2026-08-09 提取自 routers/auth.py)。"""
from __future__ import annotations

import hashlib
import hmac
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Iterable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.database import get_db
from ..models.user import BusinessRole, User
from ..services import user as user_service


_SECRET = settings.AUTH_SECRET.encode("utf-8")


def make_token(user_id: int, role: str) -> str:
    payload = json.dumps({"user_id": user_id, "role": role, "iat": int(__import__("time").time())})
    payload_b64 = urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = hmac.new(_SECRET, payload_b64.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload_b64}.{sig}"


def verify_token(token: str) -> dict | None:
    try:
        payload_b64, sig = token.split(".", 1)
        expected = hmac.new(_SECRET, payload_b64.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected):
            return None
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        return json.loads(urlsafe_b64decode(payload_b64))
    except Exception:
        return None


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 Authorization: Bearer <token> 解析当前用户。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not logged in")
    payload = verify_token(authorization[7:])
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    user = await user_service.get_user(db, payload["user_id"])
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return user


# 平台管理员业务角色(用于 admin/* 端点)
_ADMIN_BUSINESS_ROLES: frozenset[str] = frozenset({
    BusinessRole.PLATFORM_ADMIN.value,
})


def require_admin(
    user: User = Depends(get_current_user),
) -> User:
    """只允许平台管理员。"""
    if user.business_role not in _ADMIN_BUSINESS_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return user


def require_roles(*roles: str):
    """只允许指定 business_role 之一。"""
    allowed = frozenset(roles)

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.business_role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"requires one of: {sorted(allowed)}",
            )
        return user

    return _dep


def require_self_or_admin(target_user_id: int, user: User) -> None:
    """校验:目标用户必须是当前用户,或当前用户是管理员。"""
    if user.id == target_user_id:
        return
    if user.business_role in _ADMIN_BUSINESS_ROLES:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "not your resource")
