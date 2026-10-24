"""Authentication routes."""

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from base64 import urlsafe_b64decode, urlsafe_b64encode

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user, make_token, verify_token
from ..core.config import settings
from ..core.database import get_db
from ..core.logging import get_audit_logger
from ..models.business import PhoneVerificationCode
from ..models.user import BusinessRole, User, UserRole
from ..schemas.auth import (
    AdminLoginRequest,
    ReviewLoginRequest,
    SmsCodeRequest,
    SmsLoginRequest,
    WechatLoginRequest,
    WechatLoginResponse,
    WechatPhoneLoginRequest,
)
from ..schemas.user import AgreementRequest, AgreementStatus, UserCreate
from ..services import user as user_service
from ..services import wechat_pay
from ..services.wechat_pay import WeChatPayError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

audit_log = get_audit_logger()

_SECRET = settings.AUTH_SECRET.encode("utf-8")
_password_attempts = {}

_DEMO_ACCOUNTS = {
    "18800000000": (UserRole.ADMIN, BusinessRole.PLATFORM_ADMIN),
    "18800000001": (UserRole.CUSTOMER, BusinessRole.CUSTOMER),
    "18800000002": (UserRole.REPAIRER, BusinessRole.REPAIRER),
    "18800000003": (UserRole.REPAIRER, BusinessRole.SECOND_RECEIVER),
    "18800000004": (UserRole.ADMIN, BusinessRole.STORE_MANAGER),
    "18800000005": (UserRole.ADMIN, BusinessRole.CITY_MANAGER),
    "18800000006": (UserRole.CUSTOMER, BusinessRole.PROMOTION_MANAGER),
    "18800000007": (UserRole.ADMIN, BusinessRole.TECH_SUPPORT),
    "18800000008": (UserRole.ADMIN, BusinessRole.FINANCE),
    "18800000999": (UserRole.REPAIRER, BusinessRole.REPAIRER),
}


# Backward-compat aliases (legacy imports).
_make_token = make_token
_verify_token = verify_token


def _parse_demo_code(data: WechatLoginRequest) -> tuple[str, str, str]:
    parts = data.code.split(":")
    phone = data.phone or (parts[0] if parts else "")
    name = data.name or (parts[1] if len(parts) > 1 else f"user{phone[-4:]}")
    role_str = data.role or (parts[2] if len(parts) > 2 else "customer")
    if not phone:
        raise HTTPException(400, "phone is required")
    return phone, name, role_str


async def _save_openid_if_available(
    db: AsyncSession,
    user: User,
    wx_code: str | None,
) -> None:
    if not wx_code:
        return
    try:
        openid = wechat_pay.exchange_js_code(wx_code)
    except WeChatPayError:
        return

    existing = (
        await db.execute(select(User).where(User.wechat_openid == openid, User.id != user.id))
    ).scalar_one_or_none()
    if existing:
        return

    user.wechat_openid = openid
    await db.commit()
    await db.refresh(user)


async def _login_with_phone(
    db: AsyncSession,
    phone: str,
    name: str,
    role_str: str,
    wx_code: str | None = None,
    referral_code: str | None = None,
) -> WechatLoginResponse:
    demo_identity = _DEMO_ACCOUNTS.get(phone)
    role = demo_identity[0] if demo_identity else UserRole.CUSTOMER
    business_role = demo_identity[1] if demo_identity else BusinessRole.CUSTOMER

    user = await user_service.get_user_by_phone(db, phone)
    if not user:
        user = await user_service.create_user(
            db,
            UserCreate(
                phone=phone,
                name=name,
                role=role,
                business_role=business_role,
                is_promotion_manager=business_role == BusinessRole.PROMOTION_MANAGER,
            ),
        )
    if not user.is_active or user.is_pending_deletion:
        raise HTTPException(403, "账号已停用")
    await user_service.bind_referrer(db, user, referral_code)
    await _save_openid_if_available(db, user, wx_code)
    if settings.DEBUG and settings.ALLOW_DEMO_LOGIN and phone == settings.WECHAT_REVIEW_PHONE.strip():
        await _refresh_review_demo_wallet(db, user)

    # 2026-08-14: 记录登录时间(覆盖 4 个登录端点:/wechat-login / review-login / wechat-phone-login / sms/login)
    # 用 update() 显式 SQL,避免与前面 _save_openid/_refresh_review_demo_wallet 的 commit 冲突
    from sqlalchemy import update
    await db.execute(
        update(User).where(User.id == user.id).values(last_login_at=datetime.now(timezone.utc))
    )
    await db.commit()

    return WechatLoginResponse(
        token=_make_token(user.id, user.role.value, user.auth_version),
        user=_user_payload(user),
    )


async def _refresh_review_demo_wallet(db: AsyncSession, user: User) -> None:
    from ..models.ledger import LedgerType
    from ..models.withdrawal import Withdrawal, WithdrawalStatus
    from ..services import safety
    from ..services import wallet as wallet_service

    pending = (
        await db.execute(
            select(Withdrawal)
            .where(
                Withdrawal.user_id == user.id,
                Withdrawal.status == WithdrawalStatus.PENDING,
            )
            .order_by(Withdrawal.id)
        )
    ).scalars().all()
    for item in pending:
        await wallet_service.review_withdrawal(
            db,
            item.id,
            "reject",
            "审核体验账户自动恢复",
            "manual",
        )

    wallet = await wallet_service.get_or_create_wallet(db, user.id)
    minimum = max(1.0, float(settings.WECHAT_REVIEW_MIN_BALANCE))
    if wallet.available_balance < minimum:
        await safety.safe_deposit(
            db,
            user.id,
            round(minimum - wallet.available_balance, 2),
            LedgerType.MANUAL_ADJUST,
            ref_type="review_demo",
            ref_id=user.id,
            remark="审核体验专用余额",
        )


def _user_payload(user: User) -> dict:
    return {
        "is_active": user.is_active,
        "id": user.id,
        "phone": user.phone,
        "name": user.name,
        "role": user.role.value,
        "business_role": user.business_role or user.role.value,
        "business_roles": user.business_roles,
        "active_business_role": user.active_business_role,
        "avatar": user.avatar,
        "is_promotion_manager": user.is_promotion_manager,
        "has_wechat_openid": bool(user.wechat_openid),
        # 2026-08-09: 协议同意状态
        "agreed_terms_version": user.agreed_terms_version,
        "agreed_privacy_version": user.agreed_privacy_version,
        "agreed_at": user.agreed_at.isoformat() if user.agreed_at else None,
        "deletion_scheduled_at": user.deletion_scheduled_at.isoformat() if user.deletion_scheduled_at else None,
        # 2026-08-14: 最后登录时间(活跃度观测)
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


# 2026-08-09: 当前生效的协议版本(必须与 docs/legal/*.md 保持一致)
CURRENT_TERMS_VERSION = "v1.0"
CURRENT_PRIVACY_VERSION = "v1.0"


@router.post("/wechat-login", response_model=WechatLoginResponse)
async def wechat_login(data: WechatLoginRequest, db: AsyncSession = Depends(get_db)):
    if not (settings.DEBUG and settings.ALLOW_DEMO_LOGIN):
        raise HTTPException(403, "请使用密码或微信手机号登录")
    phone, name, role_str = _parse_demo_code(data)
    if phone not in _DEMO_ACCOUNTS:
        raise HTTPException(403, "This endpoint is only available for configured demo accounts")
    return await _login_with_phone(db, phone, name, role_str, data.wx_code)


@router.post("/review-login", response_model=WechatLoginResponse)
async def review_login(data: ReviewLoginRequest, db: AsyncSession = Depends(get_db)):
    if not (settings.DEBUG and settings.ALLOW_DEMO_LOGIN):
        raise HTTPException(403, "请使用密码登录")
    account = settings.WECHAT_REVIEW_ACCOUNT.strip()
    password = settings.WECHAT_REVIEW_PASSWORD
    phone = settings.WECHAT_REVIEW_PHONE.strip()
    if not account or not password:
        raise HTTPException(503, "Review login is not configured")
    if not (
        hmac.compare_digest(data.account.strip(), account)
        and hmac.compare_digest(data.password, password)
    ):
        raise HTTPException(401, "Account or password is incorrect")
    if phone not in _DEMO_ACCOUNTS:
        raise HTTPException(503, "Review account is not linked to a demo user")
    return await _login_with_phone(db, phone, "功能体验师傅", "repairer", data.wx_code)


@router.post("/admin-login", response_model=WechatLoginResponse)
async def admin_login(data: AdminLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await password_login(data, request, db)
    if result.user["business_role"] != BusinessRole.PLATFORM_ADMIN.value:
        raise HTTPException(403, "仅平台管理员可登录管理后台")
    return result


@router.post("/password-login", response_model=WechatLoginResponse)
async def password_login(data: AdminLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    import asyncio
    from collections import deque
    from ..core.passwords import check_password
    key = (request.client.host if request.client else "unknown", data.account.strip())
    now = time.monotonic()
    history = _password_attempts.setdefault(key, deque())
    while history and now - history[0] > 300:
        history.popleft()
    if len(history) >= 10:
        raise HTTPException(429, "尝试次数过多，请稍后再试")
    history.append(now)
    if len(_password_attempts) > 10000:
        for stale in list(_password_attempts):
            if not _password_attempts[stale] or now - _password_attempts[stale][-1] > 300:
                _password_attempts.pop(stale, None)
    account = data.account.strip()
    phone = settings.ADMIN_WEB_PHONE if account == settings.ADMIN_WEB_ACCOUNT.strip() else account
    user = await user_service.get_user_by_phone(db, phone)
    # Run the same expensive hash for unknown accounts to avoid an identity timing oracle.
    dummy = "pbkdf2_sha256$600000$invalid$" + "0" * 64
    valid = await asyncio.to_thread(check_password, data.password, user.password_hash if user else dummy)
    if not user or not valid:
        raise HTTPException(401, "账号或密码不正确")
    if not user.is_active or user.is_pending_deletion:
        raise HTTPException(403, "账号已停用")
    if data.referral_code:
        await user_service.bind_referrer(db, user, data.referral_code)
    if data.wx_code and not user.wechat_openid:
        await _save_openid_if_available(db, user, data.wx_code)
    _password_attempts.pop(key, None)
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    return WechatLoginResponse(token=make_token(user.id, user.role.value, user.auth_version), user=_user_payload(user))


@router.post("/wechat-phone-login", response_model=WechatLoginResponse)
async def wechat_phone_login(
    data: WechatPhoneLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        phone = wechat_pay.exchange_phone_code(data.phone_code)
    except WeChatPayError as exc:
        raise HTTPException(400, f"phone authorization failed: {exc}") from exc

    if phone in _DEMO_ACCOUNTS:
        raise HTTPException(403, "该账号请使用密码登录")
    name = data.name or f"user{phone[-4:]}"
    return await _login_with_phone(db, phone, name, "customer", data.wx_code, data.referral_code)


def _sms_hash(phone: str, code: str) -> str:
    return hashlib.sha256(f"{phone}:{code}:{settings.AUTH_SECRET}".encode("utf-8")).hexdigest()


def _sms_debug_allowed() -> bool:
    """2026-10-05:调试短信只在显式允许时可用。

    之前生产 `SMS_PROVIDER=debug` 会把固定验证码直接回显在响应里,
    `POST /api/v1/auth/sms/request` + `/sms/login` 组合即可登录任意手机号账号。
    现在必须同时满足:
      * SMS_PROVIDER == "debug"
      * DEBUG 打开 且 ALLOW_SMS_DEBUG_ENDPOINT 打开
    """
    return (
        settings.SMS_PROVIDER == "debug"
        and settings.DEBUG
        and settings.ALLOW_SMS_DEBUG_ENDPOINT
    )


@router.post("/sms/request")
async def request_sms_code(data: SmsCodeRequest, db: AsyncSession = Depends(get_db)):
    # 闸门检查必须放在限流之前:通道关闭时应稳定返回 503,
    # 而不是因为上一条记录还在冷却期返回 429(会掩盖配置问题)。
    if not _sms_debug_allowed():
        # 真实短信通道未接入,或调试通道被关闭:不泄露验证码,也不静默成功
        raise HTTPException(503, "SMS provider is not configured")

    now = datetime.now(timezone.utc)
    latest = (
        await db.execute(
            select(PhoneVerificationCode)
            .where(PhoneVerificationCode.phone == data.phone)
            .order_by(PhoneVerificationCode.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest:
        created = latest.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if (now - created).total_seconds() < 60:
            raise HTTPException(429, "Please wait before requesting another code")
    code = settings.SMS_DEBUG_CODE
    item = PhoneVerificationCode(
        phone=data.phone,
        code_hash=_sms_hash(data.phone, code),
        expires_at=now + timedelta(minutes=5),
    )
    db.add(item)
    await db.commit()
    result = {"sent": True, "expires_in": 300}
    if settings.DEBUG:
        result["debug_code"] = code
    return result


@router.post("/sms/login", response_model=WechatLoginResponse)
async def sms_login(data: SmsLoginRequest, db: AsyncSession = Depends(get_db)):
    item = (
        await db.execute(
            select(PhoneVerificationCode)
            .where(
                PhoneVerificationCode.phone == data.phone,
                PhoneVerificationCode.used_at.is_(None),
            )
            .order_by(PhoneVerificationCode.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not item:
        raise HTTPException(400, "Verification code was not requested")
    expires = item.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        raise HTTPException(400, "Verification code has expired")
    item.attempts += 1
    if item.attempts > 5 or not hmac.compare_digest(item.code_hash, _sms_hash(data.phone, data.code)):
        await db.commit()
        raise HTTPException(400, "Verification code is incorrect")
    item.used_at = datetime.now(timezone.utc)
    await db.commit()
    return await _login_with_phone(
        db,
        data.phone,
        data.name or f"用户{data.phone[-4:]}",
        "customer",
        data.wx_code,
        data.referral_code,
    )


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    """当前用户信息 + 协议版本状态(2026-08-09 加)。

    客户端拿 `agreements_need_renewal` 判断是否要弹"重新同意"窗口。
    """
    payload = _user_payload(user)
    payload["agreements_current"] = {
        "terms": CURRENT_TERMS_VERSION,
        "privacy": CURRENT_PRIVACY_VERSION,
    }
    payload["agreements_need_renewal"] = (
        user.agreed_terms_version != CURRENT_TERMS_VERSION
        or user.agreed_privacy_version != CURRENT_PRIVACY_VERSION
    )
    return payload


# 2026-08-09: 协议版本管理(《个保法》要求)
@router.post("/me/agreements", response_model=AgreementStatus)
async def record_agreement(
    data: AgreementRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """记录用户对当前协议版本的同意。前端在用户勾选后调用。"""
    user.agreed_terms_version = data.terms_version
    user.agreed_privacy_version = data.privacy_version
    user.agreed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    audit_log.info(
        "用户协议同意",
        extra={
            "actor_user_id": user.id,
            "terms_version": data.terms_version,
            "privacy_version": data.privacy_version,
        },
    )
    return AgreementStatus(
        terms_version=CURRENT_TERMS_VERSION,
        privacy_version=CURRENT_PRIVACY_VERSION,
        agreed_terms=user.agreed_terms_version,
        agreed_privacy=user.agreed_privacy_version,
        need_renewal=False,
        agreed_at=user.agreed_at,
    )


# 2026-08-09: 数据访问请求(《个保法》第 45 条 — 数据可携权)
@router.post("/me/export-data")
async def export_my_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出当前用户的全部个人数据(JSON)。"""
    from sqlalchemy import select
    from ..models.order import Order
    from ..models.ledger import Ledger
    from ..models.wallet import Wallet
    from ..models.support_ticket import SupportTicket
    from ..models.business import CustomerAddress

    orders = (await db.execute(select(Order).where(Order.customer_id == user.id))).scalars().all()
    ledger = (await db.execute(select(Ledger).where(Ledger.user_id == user.id))).scalars().all()
    wallet = (await db.execute(select(Wallet).where(Wallet.user_id == user.id))).scalar_one_or_none()
    tickets = (await db.execute(select(SupportTicket).where(SupportTicket.user_id == user.id))).scalars().all()
    addresses = (await db.execute(select(CustomerAddress).where(CustomerAddress.user_id == user.id))).scalars().all()

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {
            "is_active": user.is_active,
        "id": user.id, "phone": user.phone, "name": user.name,
            "role": user.role.value, "business_role": user.business_role,
            "avatar": user.avatar, "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "agreements": {
            "terms_version": user.agreed_terms_version,
            "privacy_version": user.agreed_privacy_version,
            "agreed_at": user.agreed_at.isoformat() if user.agreed_at else None,
        },
        "orders": [
            {
                "id": o.id, "status": o.status.value, "category": o.category,
                "description": o.description, "address": o.address,
                "amount": o.amount, "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ],
        "wallet": {
            "available_balance": wallet.available_balance if wallet else 0,
            "frozen_balance": wallet.frozen_balance if wallet else 0,
            "total_income": wallet.total_income if wallet else 0,
        } if wallet else None,
        "ledger_count": len(ledger),
        "support_tickets": [{"id": t.id, "title": t.title, "status": t.status} for t in tickets],
        "addresses": [
            {"id": a.id, "contact": a.contact_name, "phone": a.contact_phone, "address": a.address}
            for a in addresses
        ],
        "note": "本数据为《个保法》第 45 条规定的可携权副本。如需更多数据请联系客服。",
    }


# 2026-08-09: 账户删除申请(《个保法》第 47 条 — 删除权)
@router.post("/me/delete")
async def request_account_deletion(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """申请删除当前账户(15 日宽限期)。"""
    if user.deletion_scheduled_at:
        return {
            "already_scheduled": True,
            "deletion_scheduled_at": user.deletion_scheduled_at.isoformat(),
            "message": "账户删除申请已提交,15 日内可撤回。",
        }
    now = datetime.now(timezone.utc)
    user.deletion_requested_at = now
    from datetime import timedelta
    user.deletion_scheduled_at = now + timedelta(days=15)
    await db.commit()
    audit_log.warning(
        "账户删除申请",
        extra={
            "actor_user_id": user.id,
            "deletion_scheduled_at": user.deletion_scheduled_at.isoformat(),
        },
    )
    return {
        "deletion_scheduled_at": user.deletion_scheduled_at.isoformat(),
        "grace_period_days": 15,
        "message": "申请已记录,15 日后系统将自动删除账户及关联数据(法律保存期内的继续保留)。如需撤回,15 日内联系客服。",
    }


@router.post("/me/cancel-deletion")
async def cancel_account_deletion(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """撤回账户删除申请(15 日宽限期内)。"""
    if not user.deletion_scheduled_at:
        return {"message": "账户未在删除流程中。"}
    user.deletion_requested_at = None
    user.deletion_scheduled_at = None
    await db.commit()
    audit_log.info(
        "账户删除撤回",
        extra={"actor_user_id": user.id},
    )
    return {"message": "已撤回删除申请。"}
