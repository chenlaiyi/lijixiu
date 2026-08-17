"""
app.core.env_validator — env 配置校验逻辑

- validate_settings(settings) 在 app 启动时 / /health/env 端点里调
- scripts/validate_env.py 复用同一个 validate() 函数,保证 app + CLI 行为一致
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PLACEHOLDER_PATTERN = re.compile(r"^FILL_|^change-me|^local-dev-secret", re.IGNORECASE)


@dataclass
class EnvReport:
    """Validation result. Reused by /health/env and the CLI."""

    mode: str
    found_path: str | None
    missing: list[str] = field(default_factory=list)
    placeholders: list[str] = field(default_factory=list)
    weak_secrets: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[str]:
        out: list[str] = []
        out.extend(f"MISSING: {k}" for k in self.missing)
        if self.mode == "strict":
            out.extend(f"PLACEHOLDER: {k}" for k in self.placeholders)
        out.extend(f"WEAK_SECRET: {k}" for k in self.weak_secrets)
        return out

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "env_file": self.found_path,
            "ok": self.ok,
            "missing": self.missing,
            "placeholders": self.placeholders,
            "weak_secrets": self.weak_secrets,
            "warnings": self.warnings,
            "errors": self.errors,
        }


ALWAYS_REQUIRED = [
    "DATABASE_URL",
    "APP_NAME",
    "DEBUG",
    "PUBLIC_BASE_URL",
    "AUTH_SECRET",
    "WECHAT_MINIPROGRAM_ENV_VERSION",
    "PAYMENT_ALLOW_MOCK",
]

PROD_REQUIRED = ALWAYS_REQUIRED + [
    "WECHAT_PAY_APPID",
    "WECHAT_PAY_MCH_ID",
    "WECHAT_PAY_API_V3_KEY",
    "WECHAT_PAY_CERT_PATH",
    "WECHAT_PAY_KEY_PATH",
    "WECHAT_PAY_NOTIFY_URL",
    "WECHAT_REFUND_NOTIFY_URL",
    "WECHAT_APP_SECRET",
    "WECHAT_TRANSFER_NOTIFY_URL",
]

RECOMMENDED = [
    "WECHAT_PAY_CERT_SERIAL_NO",
    "WECHAT_PAY_PLATFORM_CERT_PATH",
    "WECHAT_WITHDRAW_AUTO_TRANSFER",
    "SMS_PROVIDER",
    "SMS_DEBUG_CODE",
    "MYSQL_HOST",
]


def _is_placeholder(value: str) -> bool:
    return bool(PLACEHOLDER_PATTERN.search(value))


def _looks_strong(secret: str) -> bool:
    if len(secret) < 32:
        return False
    if PLACEHOLDER_PATTERN.search(secret):
        return False
    classes = sum([
        bool(re.search(r"[a-z]", secret)),
        bool(re.search(r"[A-Z]", secret)),
        bool(re.search(r"\d", secret)),
        bool(re.search(r"[^A-Za-z0-9]", secret)),
    ])
    return classes >= 2


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _find_env_file(start: Path) -> Path | None:
    cur = start.resolve()
    for _ in range(6):
        candidate = cur / ".env"
        if candidate.exists():
            return candidate
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _get(merged: dict[str, str], key: str) -> str:
    """Get with os.environ fallback to file."""
    return str(merged.get(key, "") or "").strip()


def validate_settings(
    settings: Any,
    mode: str = "dev",
    env_path: Path | None = None,
) -> EnvReport:
    """校验已加载的 Pydantic Settings 对象。

    Args:
        settings: app.core.config.settings 实例
        mode: "dev" 或 "strict"
        env_path: 用于报告 .env 文件路径;默认自动探测
    """
    if env_path is None:
        env_path = _find_env_file(Path.cwd())
    file_vars = _load_env_file(env_path) if env_path else {}

    report = EnvReport(mode=mode, found_path=str(env_path) if env_path else None)

    required = PROD_REQUIRED if mode == "strict" else ALWAYS_REQUIRED
    for key in required:
        val = _get(file_vars, key) or str(getattr(settings, key, "") or "").strip()
        if not val:
            report.missing.append(key)
            continue
        if _is_placeholder(val):
            report.placeholders.append(key)
            continue

    # AUTH_SECRET 强度
    auth_secret = _get(file_vars, "AUTH_SECRET") or str(
        getattr(settings, "AUTH_SECRET", "") or ""
    )
    if mode == "strict":
        if not _looks_strong(auth_secret):
            report.weak_secrets.append("AUTH_SECRET")
    else:
        if auth_secret and not _looks_strong(auth_secret):
            report.warnings.append(
                "AUTH_SECRET is short or looks like a default — fine for local, rotate for prod"
            )

    # 条件性检查
    public_url = _get(file_vars, "PUBLIC_BASE_URL") or str(
        getattr(settings, "PUBLIC_BASE_URL", "") or ""
    )
    if mode == "strict" and public_url and not public_url.startswith("https://"):
        report.warnings.append(f"PUBLIC_BASE_URL={public_url!r} is not https://")

    db_url = _get(file_vars, "DATABASE_URL") or str(
        getattr(settings, "DATABASE_URL", "") or ""
    )
    if mode == "strict" and db_url.startswith("sqlite"):
        report.warnings.append("DATABASE_URL uses sqlite — use MySQL in production")

    # 推荐变量缺失
    for key in RECOMMENDED:
        file_val = _get(file_vars, key)
        settings_val = str(getattr(settings, key, "") or "").strip()
        if not file_val and not settings_val:
            report.warnings.append(f"RECOMMENDED var {key} not set")

    return report


def validate_from_environ(
    mode: str = "dev",
    env_path: Path | None = None,
) -> EnvReport:
    """CLI 模式:从 .env 文件 + os.environ 校验(不需要 Settings 实例)。

    和 validate_settings 的差别:不用 Pydantic model,纯 dict 校验。
    两者结果应当一致(除非 model 默认值和 .env 实际值不一致)。
    """
    if env_path is None:
        env_path = _find_env_file(Path.cwd())
    file_vars = _load_env_file(env_path) if env_path else {}
    merged = {**os.environ, **file_vars}

    report = EnvReport(mode=mode, found_path=str(env_path) if env_path else None)
    required = PROD_REQUIRED if mode == "strict" else ALWAYS_REQUIRED
    for key in required:
        val = _get(merged, key)
        if not val:
            report.missing.append(key)
            continue
        if _is_placeholder(val):
            report.placeholders.append(key)
            continue

    auth_secret = _get(merged, "AUTH_SECRET")
    if mode == "strict":
        if not _looks_strong(auth_secret):
            report.weak_secrets.append("AUTH_SECRET")
    elif auth_secret and not _looks_strong(auth_secret):
        report.warnings.append(
            "AUTH_SECRET is short or looks like a default — fine for local, rotate for prod"
        )

    public_url = _get(merged, "PUBLIC_BASE_URL")
    if mode == "strict" and public_url and not public_url.startswith("https://"):
        report.warnings.append(f"PUBLIC_BASE_URL={public_url!r} is not https://")

    db_url = _get(merged, "DATABASE_URL")
    if mode == "strict" and db_url.startswith("sqlite"):
        report.warnings.append("DATABASE_URL uses sqlite — use MySQL in production")

    for key in RECOMMENDED:
        if not _get(merged, key):
            report.warnings.append(f"RECOMMENDED var {key} not set")

    return report
