"""
Tests for app.core.env_validator (the module behind scripts/validate_env.py)

Covers:
- dev mode: missing required => error, placeholders => warning only
- strict mode: missing OR placeholder => error
- weak AUTH_SECRET detection
- non-https PUBLIC_BASE_URL warning
- sqlite DATABASE_URL warning in strict
- file-not-found handling
- pure-function behavior (no I/O when given a path + env dict)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core import env_validator  # noqa: E402


def _write_env(tmp_path: Path, lines: list[str]) -> Path:
    p = tmp_path / ".env"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


# ---------- dev mode ----------


def test_dev_mode_passes_for_complete_dev_env(tmp_path: Path) -> None:
    p = _write_env(tmp_path, [
        "DATABASE_URL=sqlite+aiosqlite:///./xiulijiu.db",
        "APP_NAME=test",
        "DEBUG=true",
        "PUBLIC_BASE_URL=http://localhost:8000",
        "AUTH_SECRET=local-dev-only-rotate-before-prod-32b",
        "WECHAT_MINIPROGRAM_ENV_VERSION=trial",
        "PAYMENT_ALLOW_MOCK=true",
    ])
    r = env_validator.validate_from_environ(env_path=p, mode="dev")
    assert r.ok, f"expected OK, got errors: {r.errors}"
    assert not r.missing


def test_dev_mode_flags_missing_required_as_error(tmp_path: Path) -> None:
    p = _write_env(tmp_path, [
        "DATABASE_URL=sqlite+aiosqlite:///./xiulijiu.db",
        # APP_NAME 故意漏
        "DEBUG=true",
    ])
    r = env_validator.validate_from_environ(env_path=p, mode="dev")
    assert "APP_NAME" in r.missing
    assert not r.ok


def test_dev_mode_treats_placeholder_as_warning_only(tmp_path: Path) -> None:
    p = _write_env(tmp_path, [
        "DATABASE_URL=sqlite+aiosqlite:///./xiulijiu.db",
        "APP_NAME=test",
        "DEBUG=true",
        "PUBLIC_BASE_URL=https://x.iddg.cn",
        "AUTH_SECRET=local-dev-secret-please-rotate-32+chars",
        "WECHAT_MINIPROGRAM_ENV_VERSION=trial",
        "PAYMENT_ALLOW_MOCK=true",
    ])
    r = env_validator.validate_from_environ(env_path=p, mode="dev")
    # placeholder AUTH_SECRET 在 dev 不算 error
    assert r.ok
    assert "AUTH_SECRET" in r.placeholders


# ---------- strict mode ----------


def test_strict_mode_flags_placeholders_as_error(tmp_path: Path) -> None:
    p = _write_env(tmp_path, [
        "DATABASE_URL=mysql+aiomysql://u:p@mysql:3306/xiulijiu",
        "APP_NAME=test",
        "DEBUG=false",
        "PUBLIC_BASE_URL=https://x.iddg.cn",
        "AUTH_SECRET=this-is-a-strong-enough-secret-32-chars-min-x",
        "WECHAT_MINIPROGRAM_ENV_VERSION=release",
        "PAYMENT_ALLOW_MOCK=false",
        "WECHAT_PAY_APPID=wx123",
        "WECHAT_PAY_MCH_ID=FILL_MCH_ID_X",  # placeholder
        "WECHAT_PAY_API_V3_KEY=a-real-32-byte-key-not-placeholder",
        "WECHAT_PAY_CERT_PATH=cert/apiclient_cert.pem",
        "WECHAT_PAY_KEY_PATH=cert/apiclient_key.pem",
        "WECHAT_PAY_NOTIFY_URL=https://x.iddg.cn/api/v1/payment/wechat/notify",
        "WECHAT_REFUND_NOTIFY_URL=https://x.iddg.cn/api/v1/payment/wechat/refund-notify",
        "WECHAT_APP_SECRET=real-app-secret",
        "WECHAT_TRANSFER_NOTIFY_URL=https://x.iddg.cn/api/v1/wallet/wechat/transfer-notify",
    ])
    r = env_validator.validate_from_environ(env_path=p, mode="strict")
    assert "WECHAT_PAY_MCH_ID" in r.placeholders
    assert not r.ok


def test_strict_mode_flags_weak_auth_secret(tmp_path: Path) -> None:
    p = _write_env(tmp_path, [
        "DATABASE_URL=mysql+aiomysql://u:p@mysql:3306/xiulijiu",
        "APP_NAME=test",
        "DEBUG=false",
        "PUBLIC_BASE_URL=https://x.iddg.cn",
        "AUTH_SECRET=short",  # 太短
        "WECHAT_MINIPROGRAM_ENV_VERSION=release",
        "PAYMENT_ALLOW_MOCK=false",
        "WECHAT_PAY_APPID=wx123",
        "WECHAT_PAY_MCH_ID=1481119632",
        "WECHAT_PAY_API_V3_KEY=a-real-32-byte-key-not-placeholder",
        "WECHAT_PAY_CERT_PATH=cert/apiclient_cert.pem",
        "WECHAT_PAY_KEY_PATH=cert/apiclient_key.pem",
        "WECHAT_PAY_NOTIFY_URL=https://x.iddg.cn/api/v1/payment/wechat/notify",
        "WECHAT_REFUND_NOTIFY_URL=https://x.iddg.cn/api/v1/payment/wechat/refund-notify",
        "WECHAT_APP_SECRET=real-app-secret",
        "WECHAT_TRANSFER_NOTIFY_URL=https://x.iddg.cn/api/v1/wallet/wechat/transfer-notify",
    ])
    r = env_validator.validate_from_environ(env_path=p, mode="strict")
    assert "AUTH_SECRET" in r.weak_secrets


def test_strict_mode_warns_on_sqlite(tmp_path: Path) -> None:
    p = _write_env(tmp_path, [
        "DATABASE_URL=sqlite+aiosqlite:///./xiulijiu.db",
        "APP_NAME=test",
        "DEBUG=false",
        "PUBLIC_BASE_URL=https://x.iddg.cn",
        "AUTH_SECRET=this-is-a-strong-enough-secret-32-chars-min-x",
        "WECHAT_MINIPROGRAM_ENV_VERSION=release",
        "PAYMENT_ALLOW_MOCK=false",
        "WECHAT_PAY_APPID=wx123",
        "WECHAT_PAY_MCH_ID=1481119632",
        "WECHAT_PAY_API_V3_KEY=a-real-32-byte-key-not-placeholder",
        "WECHAT_PAY_CERT_PATH=cert/apiclient_cert.pem",
        "WECHAT_PAY_KEY_PATH=cert/apiclient_key.pem",
        "WECHAT_PAY_NOTIFY_URL=https://x.iddg.cn/api/v1/payment/wechat/notify",
        "WECHAT_REFUND_NOTIFY_URL=https://x.iddg.cn/api/v1/payment/wechat/refund-notify",
        "WECHAT_APP_SECRET=real-app-secret",
        "WECHAT_TRANSFER_NOTIFY_URL=https://x.iddg.cn/api/v1/wallet/wechat/transfer-notify",
    ])
    r = env_validator.validate_from_environ(env_path=p, mode="strict")
    assert any("sqlite" in w for w in r.warnings)


def test_strict_mode_warns_on_http_public_url(tmp_path: Path) -> None:
    p = _write_env(tmp_path, [
        "DATABASE_URL=mysql+aiomysql://u:p@mysql:3306/xiulijiu",
        "APP_NAME=test",
        "DEBUG=false",
        "PUBLIC_BASE_URL=http://insecure.example.com",  # 故意非 https
        "AUTH_SECRET=this-is-a-strong-enough-secret-32-chars-min-x",
        "WECHAT_MINIPROGRAM_ENV_VERSION=release",
        "PAYMENT_ALLOW_MOCK=false",
        "WECHAT_PAY_APPID=wx123",
        "WECHAT_PAY_MCH_ID=1481119632",
        "WECHAT_PAY_API_V3_KEY=a-real-32-byte-key-not-placeholder",
        "WECHAT_PAY_CERT_PATH=cert/apiclient_cert.pem",
        "WECHAT_PAY_KEY_PATH=cert/apiclient_key.pem",
        "WECHAT_PAY_NOTIFY_URL=https://x.iddg.cn/api/v1/payment/wechat/notify",
        "WECHAT_REFUND_NOTIFY_URL=https://x.iddg.cn/api/v1/payment/wechat/refund-notify",
        "WECHAT_APP_SECRET=real-app-secret",
        "WECHAT_TRANSFER_NOTIFY_URL=https://x.iddg.cn/api/v1/wallet/wechat/transfer-notify",
    ])
    r = env_validator.validate_from_environ(env_path=p, mode="strict")
    assert any("https" in w for w in r.warnings)


# ---------- misc ----------


def test_env_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """env_path 给定但文件不存在时,found_path 仍回显(让用户看到找的是哪儿)

    monkeypatch 清掉 process 里的 os.environ,免得被之前 test 塞的变量污染。
    """
    import os as _os
    for k in list(_os.environ.keys()):
        monkeypatch.delenv(k, raising=False)
    r = env_validator.validate_from_environ(env_path=Path("/nonexistent/.env"), mode="dev")
    # 全部 ALWAYS_REQUIRED 都该 missing
    assert "DATABASE_URL" in r.missing
    assert "WECHAT_PAY_APPID" not in r.missing  # strict 才要求
    assert len(r.missing) >= 6


def test_pure_function_no_side_effects(tmp_path: Path) -> None:
    """validate() should not touch os.environ or print anything."""
    p = _write_env(tmp_path, [
        "DATABASE_URL=sqlite+aiosqlite:///./xiulijiu.db",
        "APP_NAME=x",
        "DEBUG=true",
        "PUBLIC_BASE_URL=http://localhost:8000",
        "AUTH_SECRET=a",
        "WECHAT_MINIPROGRAM_ENV_VERSION=trial",
        "PAYMENT_ALLOW_MOCK=true",
    ])
    environ_backup = dict(__import__("os").environ)
    r = env_validator.validate_from_environ(env_path=p, mode="dev")
    assert __import__("os").environ == environ_backup
    # 没设 AUTH_SECRET 强度
    assert "AUTH_SECRET" in r.missing or r.warnings


def test_comment_and_blank_lines_ignored(tmp_path: Path) -> None:
    p = _write_env(tmp_path, [
        "# this is a comment",
        "",
        "DATABASE_URL=sqlite+aiosqlite:///./xiulijiu.db",
        "# APP_NAME=commented-out",
        "APP_NAME=actual",
        "DEBUG=true",
        "PUBLIC_BASE_URL=http://localhost:8000",
        "AUTH_SECRET=local-dev-secret-please-rotate-32+chars",
        "WECHAT_MINIPROGRAM_ENV_VERSION=trial",
        "PAYMENT_ALLOW_MOCK=true",
    ])
    r = env_validator.validate_from_environ(env_path=p, mode="dev")
    assert "APP_NAME" not in r.missing


def test_quoted_value_unwrapped(tmp_path: Path) -> None:
    p = _write_env(tmp_path, [
        "DATABASE_URL=sqlite+aiosqlite:///./xiulijiu.db",
        'APP_NAME="quoted-app-name"',
        "DEBUG=true",
        "PUBLIC_BASE_URL=http://localhost:8000",
        "AUTH_SECRET=local-dev-secret-please-rotate-32+chars",
        "WECHAT_MINIPROGRAM_ENV_VERSION=trial",
        "PAYMENT_ALLOW_MOCK=true",
    ])
    r = env_validator.validate_from_environ(env_path=p, mode="dev")
    assert "APP_NAME" not in r.missing


def test_placeholder_detection_various_patterns(tmp_path: Path) -> None:
    p = _write_env(tmp_path, [
        "DATABASE_URL=sqlite+aiosqlite:///./xiulijiu.db",
        "APP_NAME=test",
        "DEBUG=true",
        "PUBLIC_BASE_URL=http://localhost:8000",
        "AUTH_SECRET=change-me-to-a-long-random-secret",
        "WECHAT_MINIPROGRAM_ENV_VERSION=trial",
        "PAYMENT_ALLOW_MOCK=true",
    ])
    r = env_validator.validate_from_environ(env_path=p, mode="dev")
    assert "AUTH_SECRET" in r.placeholders


# ---------- 小程序码 env_version(2026-10-07) ----------


def _strict_env_lines(env_version: str) -> list[str]:
    """一份除 env_version 外都能过 strict 的完整 .env。

    必须写全 `SMS_PROVIDER` / `ALLOW_SMS_DEBUG_ENDPOINT`:别的测试模块会把
    `debug`+`true` 留在 `os.environ` 里,而 `validate_from_environ` 会合并
    `os.environ`,漏写就会串进 SMS 违规(全量 pytest 时才暴露)。
    """
    return [
        "DATABASE_URL=mysql+aiomysql://u:p@mysql:3306/xiulijiu",
        "APP_NAME=test",
        "DEBUG=false",
        "PUBLIC_BASE_URL=https://x.iddg.cn",
        "AUTH_SECRET=this-is-a-strong-enough-secret-32-chars-min-x",
        f"WECHAT_MINIPROGRAM_ENV_VERSION={env_version}",
        "PAYMENT_ALLOW_MOCK=false",
        "SMS_PROVIDER=aliyun",
        "ALLOW_SMS_DEBUG_ENDPOINT=false",
        "WECHAT_PAY_APPID=wx123",
        "WECHAT_PAY_MCH_ID=1481119632",
        "WECHAT_PAY_API_V3_KEY=a-real-32-byte-key-not-placeholder",
        "WECHAT_PAY_CERT_PATH=cert/apiclient_cert.pem",
        "WECHAT_PAY_KEY_PATH=cert/apiclient_key.pem",
        "WECHAT_PAY_NOTIFY_URL=https://x.iddg.cn/api/v1/payment/wechat/notify",
        "WECHAT_REFUND_NOTIFY_URL=https://x.iddg.cn/api/v1/payment/wechat/refund-notify",
        "WECHAT_APP_SECRET=real-app-secret",
        "WECHAT_TRANSFER_NOTIFY_URL=https://x.iddg.cn/api/v1/wallet/wechat/transfer-notify",
    ]


def test_strict_mode_passes_with_release_env_version(tmp_path: Path) -> None:
    p = _write_env(tmp_path, _strict_env_lines("release"))
    r = env_validator.validate_from_environ(env_path=p, mode="strict")
    assert r.ok, f"expected OK, got errors: {r.errors}"
    assert not any("MINIPROGRAM" in w for w in r.warnings)


def test_strict_mode_allows_trial_but_warns(tmp_path: Path) -> None:
    """正式版发布之前 trial 是唯一可用取值,不能拦;但必须提示。"""
    p = _write_env(tmp_path, _strict_env_lines("trial"))
    r = env_validator.validate_from_environ(env_path=p, mode="strict")
    assert r.ok, f"trial 不该让 strict 失败(会逼出出不了码的配置),errors={r.errors}"
    assert any("WECHAT_MINIPROGRAM_ENV_VERSION=trial" in w for w in r.warnings)


@pytest.mark.parametrize("value", ["develop", "production", "TRIAL2"])
def test_strict_mode_rejects_unusable_env_version(tmp_path: Path, value: str) -> None:
    """develop / 非法取值:线上小程序码必然打不开。"""
    p = _write_env(tmp_path, _strict_env_lines(value))
    r = env_validator.validate_from_environ(env_path=p, mode="strict")
    assert not r.ok
    assert any("WECHAT_MINIPROGRAM_ENV_VERSION" in e for e in r.errors)


def test_dev_mode_only_warns_on_trial_env_version(tmp_path: Path) -> None:
    """本地开发用 trial 是正常的,只提示不拦。"""
    p = _write_env(tmp_path, [
        "DATABASE_URL=sqlite+aiosqlite:///./xiulijiu.db",
        "APP_NAME=test",
        "DEBUG=true",
        "PUBLIC_BASE_URL=http://localhost:8000",
        "AUTH_SECRET=local-dev-only-rotate-before-prod-32b",
        "WECHAT_MINIPROGRAM_ENV_VERSION=trial",
        "PAYMENT_ALLOW_MOCK=true",
    ])
    r = env_validator.validate_from_environ(env_path=p, mode="dev")
    assert r.ok, f"dev 模式不该拦,errors={r.errors}"
    assert any("WECHAT_MINIPROGRAM_ENV_VERSION" in w for w in r.warnings)


def test_validate_settings_also_catches_develop(tmp_path: Path) -> None:
    """validate_settings(启动 / /health/env 走的路径)也要命中同一规则。"""

    class _Settings:
        WECHAT_MINIPROGRAM_ENV_VERSION = "develop"

    r = env_validator.validate_settings(
        _Settings(), mode="strict", env_path=tmp_path / "missing.env"
    )
    assert any("WECHAT_MINIPROGRAM_ENV_VERSION" in e for e in r.errors)

