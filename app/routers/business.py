"""Addresses, proxy access, warranties, wages, and domestic-service APIs."""

import json
import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user, is_staff, require_staff, require_staff_or_self
from ..core.database import get_db
from ..core.config import settings
from ..models.business import (
    CustomerAddress,
    DomesticCandidate,
    DomesticContract,
    DomesticDemand,
    DomesticPaymentStage,
    DomesticWorker,
)
from ..models.order import Order
from ..models.user import User
from ..models.pay_order import PayProvider
from ..models.settlement import SettlementItem, SettlementPeriod
from ..schemas.business import (
    AccessTokenOut,
    AccessTokenRequest,
    AddressCreate,
    AddressOut,
    AddressUpdate,
    CandidateCreate,
    CandidateOut,
    CandidateUpdate,
    ClaimOrderOut,
    ClaimOrderRequest,
    ContractActionRequest,
    ContractCreate,
    ContractOut,
    DomesticDemandCreate,
    DomesticDemandOut,
    DomesticDemandUpdate,
    DomesticWorkerCreate,
    DomesticWorkerOut,
    DomesticWorkerUpdate,
    PaymentStageOut,
    PayrollCreate,
    PayrollPayRequest,
    StagePaymentRequest,
    WageOut,
    WarrantyOut,
)
from ..schemas.payment import PayCreateRequest, PayCreateResponse
from ..services import business as service
from ..services import payment as payment_service
from ..services import wechat_pay
from ..services.wechat_pay import WeChatPayError

router = APIRouter(prefix="/api/v1/business", tags=["business"])


@router.get("/addresses", response_model=list[AddressOut])
async def addresses(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05
):
    require_staff_or_self(user_id, user)
    return await service.list_addresses(db, user_id)


@router.post("/addresses", response_model=AddressOut, status_code=201)
async def create_address(
    data: AddressCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05
):
    if not is_staff(user) and data.user_id != user.id:
        raise HTTPException(403, "not your address")
    try:
        return await service.create_address(db, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/addresses/{address_id}", response_model=AddressOut)
async def update_address(
    address_id: int,
    data: AddressUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05
):
    address = await db.get(CustomerAddress, address_id)
    if not address:
        raise HTTPException(404, "Address not found")
    require_staff_or_self(address.user_id, user)
    try:
        return await service.update_address(db, address, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/orders/{order_id}/access/{purpose}", response_model=AccessTokenOut)
async def create_order_access(
    order_id: int,
    purpose: str,
    data: AccessTokenRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05:仅登录用户可签发
):
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    try:
        token, item = await service.create_access_token(db, order, purpose, user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    page = "pages/proxy/access/access"
    return AccessTokenOut(
        token=token,
        purpose=purpose,
        order_id=order.id,
        expires_at=item.expires_at,
        page=page,
        code_url=f"/api/v1/business/access/{token}/code.png",
    )


@router.get("/access/{token}")
async def resolve_order_access(token: str, db: AsyncSession = Depends(get_db)):
    try:
        item, order = await service.resolve_access_token(db, token)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    phone = order.customer_phone_snapshot or order.contact_phone or ""
    masked_phone = f"{phone[:3]}****{phone[-4:]}" if len(phone) >= 7 else ""
    return {
        "purpose": item.purpose,
        "order_id": order.id,
        "status": order.status.value,
        "description": order.description,
        "amount": order.price,
        "paid_amount": order.paid_amount,
        "contact_phone_masked": masked_phone,
        "claim_status": order.claim_status,
    }


@router.get("/access/{token}/code.png")
async def access_code(token: str, db: AsyncSession = Depends(get_db)):
    try:
        await service.resolve_access_token(db, token)
        content = wechat_pay.get_mini_program_code(token, "pages/proxy/access/access")
    except (ValueError, WeChatPayError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return Response(content=content, media_type="image/png")


@router.post("/orders/claim", response_model=ClaimOrderOut)
async def claim_order(
    data: ClaimOrderRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05
):
    if not is_staff(user) and data.user_id != user.id:
        raise HTTPException(403, "cannot claim for another user")
    try:
        order, action = await service.claim_order(db, data.token, data.user_id, data.verification_phone)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ClaimOrderOut(
        order_id=order.id,
        action=action,
        claim_status=order.claim_status,
        message="订单认领成功" if action == "claimed" else "手机号不匹配，可继续代付",
    )


@router.get("/warranties", response_model=list[WarrantyOut])
async def warranties(
    customer_id: int | None = None,
    phone: str | None = None,
    include_expired: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05
):
    if not is_staff(user):
        if customer_id is not None and customer_id != user.id:
            raise HTTPException(403, "not your warranty")
        customer_id = user.id
        phone = None
    try:
        return await service.list_warranties(db, customer_id, phone, include_expired)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/wages", response_model=list[WageOut])
async def wages(
    store_id: int | None = None,
    employee_user_id: int | None = None,
    wage_mode: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05
):
    if not is_staff(user):
        if employee_user_id is not None and employee_user_id != user.id:
            raise HTTPException(403, "not your wage")
        employee_user_id = user.id
        store_id = None
    return await service.list_wages(db, store_id, employee_user_id, wage_mode)


@router.post("/payroll")
async def create_payroll(
    data: PayrollCreate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
):
    period = await service.create_payroll(db, data)
    return {"period_id": period.id, "month": period.month, "status": period.status.value}


@router.get("/payroll")
async def list_payroll(
    store_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
):
    periods = list((await db.execute(
        select(SettlementPeriod).order_by(SettlementPeriod.month.desc())
    )).scalars().all())
    stmt = select(SettlementItem).order_by(SettlementItem.id.desc())
    if store_id:
        stmt = stmt.where(SettlementItem.store_id == store_id)
    items = list((await db.execute(stmt)).scalars().all())
    return {
        "periods": [
            {"id": item.id, "month": item.month, "status": item.status.value}
            for item in periods
        ],
        "items": [
            {
                "id": item.id,
                "period_id": item.period_id,
                "user_id": item.user_id,
                "store_id": item.store_id,
                "amount": item.amount,
                "status": item.status.value,
                "remark": item.remark,
                "paid_at": item.paid_at,
            }
            for item in items
        ],
    }


@router.post("/payroll/{period_id}/pay")
async def pay_payroll(
    period_id: int,
    data: PayrollPayRequest,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
):
    try:
        period = await service.pay_payroll(db, period_id, data.store_id, data.manager_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"period_id": period.id, "month": period.month, "status": period.status.value}


@router.get("/domestic/workers", response_model=list[DomesticWorkerOut])
async def workers(
    service_type: str | None = None,
    store_id: int | None = None,
    active: bool = True,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await service.list_workers(db, service_type, store_id, active)


@router.post("/domestic/workers", response_model=DomesticWorkerOut, status_code=201)
async def create_worker(
    data: DomesticWorkerCreate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
):
    return await service.create_worker(db, data)


@router.patch("/domestic/workers/{worker_id}", response_model=DomesticWorkerOut)
async def update_worker(
    worker_id: int,
    data: DomesticWorkerUpdate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
):
    worker = await db.get(DomesticWorker, worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found")
    return await service.update_worker(db, worker, data)


@router.get("/domestic/workers/{worker_id}", response_model=DomesticWorkerOut)
async def get_worker(
    worker_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    worker = await db.get(DomesticWorker, worker_id)
    if not worker or not worker.active:
        raise HTTPException(404, "Worker not found")
    return worker


@router.get("/domestic/demands", response_model=list[DomesticDemandOut])
async def demands(
    customer_id: int | None = None,
    store_id: int | None = None,
    service_type: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05
):
    if not is_staff(user):
        if customer_id is not None and customer_id != user.id:
            raise HTTPException(403, "not your demand")
        customer_id = user.id
        store_id = None
    return await service.list_demands(db, customer_id, store_id, service_type, status)


@router.post("/domestic/demands", response_model=DomesticDemandOut, status_code=201)
async def create_demand(
    data: DomesticDemandCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05
):
    if not is_staff(user) and data.customer_id != user.id:
        raise HTTPException(403, "not your demand")
    try:
        return await service.create_demand(db, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/domestic/demands/{demand_id}/media", response_model=DomesticDemandOut)
async def upload_demand_media(
    demand_id: int,
    media_type: str = Form(...),
    duration: int | None = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05
):
    demand = await db.get(DomesticDemand, demand_id)
    if not demand:
        raise HTTPException(404, "Demand not found")
    require_staff_or_self(demand.customer_id, user)
    if media_type not in ("audio", "image"):
        raise HTTPException(400, "Only audio and image are supported")
    content = await file.read()
    if not content or len(content) > 30 * 1024 * 1024:
        raise HTTPException(400, "File must be between 1 byte and 30MB")
    allowed = {
        "audio": {".mp3", ".m4a", ".aac", ".wav"},
        "image": {".jpg", ".jpeg", ".png", ".webp", ".heic"},
    }
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed[media_type]:
        ext = ".m4a" if media_type == "audio" else ".jpg"
    root = Path(settings.UPLOAD_DIR)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / root
    rel_dir = Path("domestic") / str(demand_id)
    target_dir = root / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{media_type}_{time.strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}{ext}"
    (target_dir / filename).write_bytes(content)
    try:
        media = json.loads(demand.media_json or "[]")
        if not isinstance(media, list):
            media = []
    except Exception:
        media = []
    media.append({
        "type": media_type,
        "url": f"/uploads/{rel_dir.as_posix()}/{filename}",
        "name": file.filename or filename,
        "size": len(content),
        "duration": duration or 0,
    })
    demand.media_json = json.dumps(media, ensure_ascii=False)
    await db.commit()
    await db.refresh(demand)
    return demand


@router.patch("/domestic/demands/{demand_id}", response_model=DomesticDemandOut)
async def update_demand(
    demand_id: int,
    data: DomesticDemandUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05
):
    demand = await db.get(DomesticDemand, demand_id)
    if not demand:
        raise HTTPException(404, "Demand not found")
    require_staff_or_self(demand.customer_id, user)
    return await service.update_demand(db, demand, data)


@router.get("/domestic/demands/{demand_id}/candidates", response_model=list[CandidateOut])
async def candidates(
    demand_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05
):
    demand = await db.get(DomesticDemand, demand_id)
    if demand:
        require_staff_or_self(demand.customer_id, user)
    rows = await db.execute(
        select(DomesticCandidate)
        .where(DomesticCandidate.demand_id == demand_id)
        .order_by(DomesticCandidate.id.desc())
    )
    return list(rows.scalars().all())


@router.post("/domestic/demands/{demand_id}/candidates", response_model=CandidateOut)
async def add_candidate(
    demand_id: int,
    data: CandidateCreate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
):
    demand = await db.get(DomesticDemand, demand_id)
    if not demand:
        raise HTTPException(404, "Demand not found")
    try:
        return await service.add_candidate(db, demand, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/domestic/candidates/{candidate_id}", response_model=CandidateOut)
async def update_candidate(
    candidate_id: int,
    data: CandidateUpdate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
):
    candidate = await db.get(DomesticCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    return await service.update_candidate(db, candidate, data)


@router.post("/domestic/demands/{demand_id}/contract", response_model=ContractOut)
async def create_contract(
    demand_id: int,
    data: ContractCreate,
    db: AsyncSession = Depends(get_db),
    _staff: User = Depends(require_staff),
):
    demand = await db.get(DomesticDemand, demand_id)
    if not demand:
        raise HTTPException(404, "Demand not found")
    try:
        return await service.create_contract(db, demand, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/domestic/contracts", response_model=list[ContractOut])
async def contracts(
    customer_id: int | None = None,
    store_id: int | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05
):
    if not is_staff(user):
        if customer_id is not None and customer_id != user.id:
            raise HTTPException(403, "not your contract")
        customer_id = user.id
        store_id = None
    stmt = select(DomesticContract)
    if customer_id:
        stmt = stmt.where(DomesticContract.customer_id == customer_id)
    if store_id:
        stmt = stmt.where(DomesticContract.store_id == store_id)
    if status:
        stmt = stmt.where(DomesticContract.status == status)
    rows = await db.execute(stmt.order_by(DomesticContract.id.desc()))
    return list(rows.scalars().all())


@router.get("/domestic/contracts/{contract_id}/stages", response_model=list[PaymentStageOut])
async def contract_stages(
    contract_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05
):
    contract = await db.get(DomesticContract, contract_id)
    if contract:
        require_staff_or_self(contract.customer_id, user)
    rows = await db.execute(
        select(DomesticPaymentStage)
        .where(DomesticPaymentStage.contract_id == contract_id)
        .order_by(DomesticPaymentStage.id)
    )
    return list(rows.scalars().all())


@router.post("/domestic/stages/{stage_id}/payment", response_model=PayCreateResponse)
async def pay_stage(
    stage_id: int,
    data: StagePaymentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05
):
    if not is_staff(user) and data.user_id != user.id:
        raise HTTPException(403, "cannot pay for another user")
    stage = await db.get(DomesticPaymentStage, stage_id)
    if not stage or stage.status == "paid":
        raise HTTPException(400, "Payment stage is unavailable")
    contract = await db.get(DomesticContract, stage.contract_id)
    if not contract:
        raise HTTPException(404, "Contract not found")
    request = PayCreateRequest(
        order_id=contract.order_id,
        user_id=data.user_id,
        amount=stage.amount,
        provider=PayProvider(data.provider),
        js_code=data.js_code,
    )
    try:
        pay_order = await payment_service.create_payment(db, request)
        stage.pay_order_id = pay_order.id
        await db.commit()
        intent = await payment_service.create_payment_intent(db, pay_order, request)
    except (ValueError, WeChatPayError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return PayCreateResponse(
        pay_order_id=pay_order.id,
        pay_url=intent.pay_url,
        status="pending",
        amount=pay_order.amount,
        provider=pay_order.provider,
        payment_params=intent.payment_params or None,
    )


@router.post("/domestic/contracts/{contract_id}/action", response_model=ContractOut)
async def contract_action(
    contract_id: int,
    data: ContractActionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # 2026-10-05
):
    contract = await db.get(DomesticContract, contract_id)
    if not contract:
        raise HTTPException(404, "Contract not found")
    try:
        return await service.contract_action(db, contract, data.action, data.remark)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
