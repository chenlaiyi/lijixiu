"""立即修平台 — FastAPI 入口 v8（认证+小程序前端）"""

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

from .core.config import settings
from .core.database import async_session, engine, init_db
from .core.env_validator import validate_settings
from .core.logging import configure_logging
from .core.middleware import RequestIDMiddleware, metrics as prom_metrics

# 启动时配置日志(必须在其他模块 logger 使用前)
configure_logging()
from .models.alert_event import AlertSeverity
from .models.order import Order, OrderStatus
from .models.reconciliation import ReconcileStatus
from .routers import (
    admin,
    auth,
    business,
    finance,
    order,
    payment,
    region,
    referral,
    repairer,
    service_package,
    service_area,
    store,
    support,
    user,
    wallet,
)
from .services.order import timeout_reassign
from .services.service_area import sync_xiamen_service_areas

_START_TIME = time.time()
_H5_DIR = Path(__file__).resolve().parent.parent / "h5"
_ADMIN_DIR = Path(__file__).resolve().parent.parent / "admin-web"
_UPLOAD_DIR = Path(settings.UPLOAD_DIR)
if not _UPLOAD_DIR.is_absolute():
    _UPLOAD_DIR = Path(__file__).resolve().parent.parent / _UPLOAD_DIR
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def _timeout_reassign_loop():
    while True:
        try:
            await asyncio.sleep(60)
            async with async_session() as db:
                stmt = select(Order).where(Order.status == OrderStatus.STORE_PENDING)
                for o in (await db.execute(stmt)).scalars().all():
                    try:
                        await timeout_reassign(db, o)
                    except Exception:
                        pass
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 2026-08-09:启动时可选 strict env 校验。生产建议开。
    if settings.STRICT_ENV_ON_STARTUP:
        report = validate_settings(settings, mode="strict")
        if not report.ok:
            from .core.logging import get_logger
            log = get_logger("xiulijiu.startup")
            log.error(
                "STRICT_ENV_ON_STARTUP enabled but env validation failed",
                extra={
                    "missing": report.missing,
                    "placeholders": report.placeholders,
                    "weak_secrets": report.weak_secrets,
                    "warnings": report.warnings,
                },
            )
            raise RuntimeError(
                f"env validation failed (STRICT_ENV_ON_STARTUP=true): "
                f"{len(report.errors)} errors. Run `python scripts/validate_env.py --strict`"
            )
        else:
            from .core.logging import get_logger
            get_logger("xiulijiu.startup").info(
                "env validation passed (strict mode)",
                extra={"warnings": report.warnings},
            )

    await init_db()
    async with async_session() as db:
        await sync_xiamen_service_areas(db)
        from .services.repairer import ensure_role_profiles
        await ensure_role_profiles(db)
        await db.commit()
    task = asyncio.create_task(_timeout_reassign_loop())
    yield
    task.cancel()


app = FastAPI(
    title="立即修平台",
    description="上门维修 O2O 平台后端 — 生产版本",
    version="1.0.0",
    lifespan=lifespan,
)

# 中间件
app.add_middleware(RequestIDMiddleware)

if _H5_DIR.exists():
    app.mount("/h5", StaticFiles(directory=_H5_DIR, html=True), name="h5")
if _ADMIN_DIR.exists():
    app.mount("/admin", StaticFiles(directory=_ADMIN_DIR, html=True), name="admin")
app.mount("/uploads", StaticFiles(directory=_UPLOAD_DIR), name="uploads")

# 路由
app.include_router(auth.router)
app.include_router(business.router)
app.include_router(user.router)
app.include_router(referral.router)
app.include_router(repairer.router)
app.include_router(order.router)
app.include_router(region.router)
app.include_router(store.router)
app.include_router(finance.router)
app.include_router(wallet.router)
app.include_router(admin.router)
app.include_router(payment.router)
app.include_router(support.router)
app.include_router(service_package.router)
app.include_router(service_area.router)


@app.get("/")
async def root():
    return {
        "service": "立即修平台",
        "version": "1.0.0",
        "status": "running",
        "uptime_seconds": round(time.time() - _START_TIME),
    }


@app.get("/health")
async def health():
    """系统健康检查"""
    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "uptime_seconds": round(time.time() - _START_TIME),
        "version": "1.0.0",
    }


@app.get("/health/env")
async def health_env(mode: str = "dev"):
    """
    环境变量完整性自检(2026-08-09 新增)。

    默认 dev 模式只报告,strict 模式才会把 placeholder / 弱 secret 算 fail。
    永远返回 200,这样不会触发监控告警;业务方根据 `ok` 字段判断。

    Query params:
        mode: "dev" (默认) 或 "strict"
    """
    from fastapi import HTTPException
    if mode not in ("dev", "strict"):
        raise HTTPException(400, f"mode must be 'dev' or 'strict', got {mode!r}")
    report = validate_settings(settings, mode=mode)
    body = report.to_dict()
    body["uptime_seconds"] = round(time.time() - _START_TIME, 2)
    return body


# 2026-10-07:业务指标采集抽到 app/services/business_metrics.py,
# 让后台概览(/api/v1/admin/metrics,Bearer)与 Prometheus(/metrics,basic auth)
# 共用同一份口径,同时避免 admin 路由 import main 造成的循环导入。
from .services.business_metrics import business_metrics as _business_metrics  # noqa: E402


@app.get("/metrics")
async def metrics():
    """业务指标(JSON,保留兼容)。"""
    try:
        async with async_session() as db:
            data = await _business_metrics(db)
    except Exception:
        data = {
            "orders_total": 0,
            "orders_completed": 0,
            "orders_pending": 0,
            "wallets_total": 0,
            "total_balance": 0,
            "alerts_active": -1,
            "alerts_critical": 0,
            "alerts_warning": 0,
            "last_recon_mismatch": 0,
        }

    return {
        "uptime_seconds": round(time.time() - _START_TIME, 2),
        **data,
        "total_balance": round(float(data.get("total_balance") or 0), 2),
    }


@app.get("/metrics/prom", response_class=PlainTextResponse)
async def metrics_prometheus():
    """Prometheus 文本格式指标(2026-08-09)。"""
    lines: list[str] = [prom_metrics.render_prometheus().rstrip("\n")]

    # 业务指标(与 /metrics JSON 端点共用同一采集函数)
    try:
        async with async_session() as db:
            data = await _business_metrics(db)
        orders_total = data["orders_total"]
        orders_completed = data["orders_completed"]
        orders_pending = data["orders_pending"]
        wallets_total = data["wallets_total"]
        total_balance = data["total_balance"]
        alerts_active = data["alerts_active"]
        alerts_critical = data["alerts_critical"]
        alerts_warning = data["alerts_warning"]
        last_recon_mismatch = data["last_recon_mismatch"]
    except Exception:
        orders_total = orders_completed = orders_pending = wallets_total = 0
        total_balance = alerts_active = alerts_critical = alerts_warning = last_recon_mismatch = 0

    # 2026-08-10:env 完整性(0/1),给 Prometheus alert 抓
    try:
        env_report = validate_settings(settings, mode="dev")
        env_ok = 1 if env_report.ok else 0
        env_missing = len(env_report.missing)
        env_placeholders = len(env_report.placeholders)
    except Exception:
        env_ok, env_missing, env_placeholders = 0, 0, 0

    lines.extend([
        f"xiulijiu_orders_total {orders_total}",
        f"xiulijiu_orders_completed {orders_completed}",
        f"xiulijiu_orders_pending {orders_pending}",
        f"xiulijiu_wallets_total {wallets_total}",
        f"xiulijiu_total_balance {total_balance}",
        f"xiulijiu_alerts_active {alerts_active}",
        f"xiulijiu_alerts_active_critical {alerts_critical}",
        f"xiulijiu_alerts_active_warning {alerts_warning}",
        f"xiulijiu_last_recon_mismatch {last_recon_mismatch}",
        f"xiulijiu_env_ok {env_ok}",
        f"xiulijiu_env_missing {env_missing}",
        f"xiulijiu_env_placeholders {env_placeholders}",
    ])

    body = "\n".join(lines) + "\n"
    return PlainTextResponse(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")
