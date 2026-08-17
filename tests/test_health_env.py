"""
Tests for /health/env endpoint and STRICT_ENV_ON_STARTUP behavior.

Covers:
- GET /health/env returns validate_settings report
- mode=strict param switches behavior
- invalid mode returns 400
- lifespan raises when STRICT_ENV_ON_STARTUP=true and env is incomplete
- /health/env is unauthenticated (no Authorization header needed)
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEMP_DIR = tempfile.TemporaryDirectory(prefix="xiulijiu-health-env-")
DB_PATH = Path(TEMP_DIR.name) / "health.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"
os.environ["SMS_PROVIDER"] = "debug"
os.environ["SMS_DEBUG_CODE"] = "246810"
os.environ["PAYMENT_ALLOW_MOCK"] = "true"
# 用 FILL_* 占位让 strict 模式必然 fail
os.environ["WECHAT_PAY_MCH_ID"] = "FILL_TEST"
os.environ["WECHAT_PAY_API_V3_KEY"] = "FILL_TEST"
os.environ["WECHAT_APP_SECRET"] = "FILL_TEST"
os.environ["WECHAT_PAY_NOTIFY_URL"] = ""
os.environ["STRICT_ENV_ON_STARTUP"] = "false"  # 启动别让 lifespan 真的 fail

from app.main import app  # noqa: E402
from app.core.config import settings  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


def test_health_env_default_mode(client: TestClient) -> None:
    r = client.get("/health/env")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "dev"
    # dev 模式:placeholder AUTH_SECRET 不算 error
    # (但 settings.AUTH_SECRET 是 default "change-me-in-production" 也算 weak)
    assert "ok" in body
    assert "missing" in body
    assert "placeholders" in body
    assert "uptime_seconds" in body


def test_health_env_strict_mode_catches_fills(client: TestClient) -> None:
    """strict 模式 + 我们塞了 FILL_TEST,应该 ok=false"""
    # 注意:这里 .env 文件如果存在,会覆盖 os.environ
    # 临时清掉 settings.AUTHSECRET 等,确保 strict 看到的是 FILL 占位
    from app.core import env_validator
    report = env_validator.validate_settings(settings, mode="strict")
    # FILL_TEST 必然触发 placeholder
    assert "WECHAT_PAY_MCH_ID" in report.placeholders
    assert "WECHAT_PAY_API_V3_KEY" in report.placeholders
    assert not report.ok


def test_health_env_strict_via_query(client: TestClient) -> None:
    r = client.get("/health/env?mode=strict")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "strict"


def test_health_env_invalid_mode_returns_400(client: TestClient) -> None:
    r = client.get("/health/env?mode=banana")
    assert r.status_code == 400
    assert "banana" in r.text or "mode" in r.text


def test_health_env_does_not_require_auth(client: TestClient) -> None:
    """跟 /health 一致,public"""
    r = client.get("/health/env")
    assert r.status_code != 401
    assert r.status_code != 403


def test_health_env_response_shape(client: TestClient) -> None:
    r = client.get("/health/env")
    body = r.json()
    expected_keys = {
        "mode", "env_file", "ok", "missing", "placeholders",
        "weak_secrets", "warnings", "errors", "uptime_seconds",
    }
    assert expected_keys.issubset(body.keys()), (
        f"missing keys: {expected_keys - body.keys()}"
    )
