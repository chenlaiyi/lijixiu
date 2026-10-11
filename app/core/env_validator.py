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
    "ALLOW_SMS_DEBUG_ENDPOINT",
    "MYSQL_HOST",
    # 2026-10-07:管理后台账号密码登录。不配的话后台只能用应急的 token 登录,
    # 且登录框会提示「后台登录未配置」。
    "ADMIN_WEB_ACCOUNT",
    "ADMIN_WEB_PASSWORD",
]


def _sms_debug_violation(merged: dict[str, str]) -> str | None:
    """2026-10-05:生产不允许开着调试短信通道。

    `SMS_PROVIDER=debug` + `ALLOW_SMS_DEBUG_ENDPOINT=true` 会让
    `/api/v1/auth/sms/request` 回显固定验证码,等于把任意手机号账号交出去。
    """
    provider = _get(merged, "SMS_PROVIDER").lower()
    allow = _get(merged, "ALLOW_SMS_DEBUG_ENDPOINT").lower() in {"1", "true", "yes", "on"}
    if provider == "debug" and allow:
        return (
            "SMS debug endpoint is enabled (SMS_PROVIDER=debug + "
            "ALLOW_SMS_DEBUG_ENDPOINT=true) — anyone can log in as any phone number"
        )
    return None


def _miniprogram_env_violation(merged: dict[str, str]) -> str | None:
    """2026-10-07:线上小程序码不能指向开发版,也不能是非法取值。

    `WECHAT_MINIPROGRAM_ENV_VERSION` 直接喂给微信 `getwxacodeunlimit` 的
    `env_version`(见 app/services/wechat_pay.py::get_mini_program_code)。

    - `develop`:只有开发者能打开,线上生成的推广/代理码必然是坏链接 → 硬错误;
    - `release` / `trial`:合法。`trial` 的隐患由 `_miniprogram_env_warning` 提示
      —— 小程序**正式版发布之前它仍是唯一可用的取值**(没有正式版时
      `env_version=release` 不一定出得了码),所以这里不拦,免得把部署逼进
      「要么部署失败、要么小程序码生成失败」的两难。

    这个变量过去只被检查「是否存在」,不校验取值,所以线上一直留在 `trial`。
    """
    value = _get(merged, "WECHAT_MINIPROGRAM_ENV_VERSION").lower()
    if not value or value in ("release", "trial"):
        return None
    if value == "develop":
        return (
            "WECHAT_MINIPROGRAM_ENV_VERSION=develop — production mini-program codes "
            "(wxacode) would only open for developers"
        )
    return (
        f"WECHAT_MINIPROGRAM_ENV_VERSION={value!r} is not a valid WeChat env_version "
        "(release / trial / develop)"
    )


def _miniprogram_env_warning(merged: dict[str, str]) -> str | None:
    """`trial` 在小程序正式发布后就是隐患 —— 提醒切换,但不拦部署。"""
    value = _get(merged, "WECHAT_MINIPROGRAM_ENV_VERSION").lower()
    if value == "trial":
        return (
            "WECHAT_MINIPROGRAM_ENV_VERSION=trial — mini-program codes (wxacode) point "
            "at the 体验版, which non-members cannot open; switch to release after the "
            "mini program is formally published"
        )
    return None


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


def _effective(settings: Any, file_vars: dict[str, str], key: str) -> str:
    """取「真实生效」的配置值。

    优先级与 Pydantic Settings 一致:os.environ > .env 文件 > 代码默认值。
    之前只看 file_vars,导致用环境变量覆盖 `.env`(比如部署时
    `ALLOW_SMS_DEBUG_ENDPOINT=false`)时,校验会误报。
    """
    if key in os.environ and str(os.environ[key]).strip():
        return str(os.environ[key]).strip()
    value = _get(file_vars, key)
    if value:
        return value
    return str(getattr(settings, key, "") or "").strip()


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
        val = _effective(settings, file_vars, key)
        if not val:
            report.missing.append(key)
            continue
        if _is_placeholder(val):
            report.placeholders.append(key)
            continue

    # AUTH_SECRET 强度
    auth_secret = _effective(settings, file_vars, "AUTH_SECRET")
    if mode == "strict":
        if not _looks_strong(auth_secret):
            report.weak_secrets.append("AUTH_SECRET")
    else:
        if auth_secret and not _looks_strong(auth_secret):
            report.warnings.append(
                "AUTH_SECRET is short or looks like a default — fine for local, rotate for prod"
            )

    # 条件性检查
    public_url = _effective(settings, file_vars, "PUBLIC_BASE_URL")
    if mode == "strict" and public_url and not public_url.startswith("https://"):
        report.warnings.append(f"PUBLIC_BASE_URL={public_url!r} is not https://")

    db_url = _effective(settings, file_vars, "DATABASE_URL")
    if mode == "strict" and db_url.startswith("sqlite"):
        report.warnings.append("DATABASE_URL uses sqlite — use MySQL in production")

    # 调试短信通道:strict 模式视为硬错误
    sms_violation = _sms_debug_violation(
        {
            "SMS_PROVIDER": _effective(settings, file_vars, "SMS_PROVIDER"),
            "ALLOW_SMS_DEBUG_ENDPOINT": _effective(
                settings, file_vars, "ALLOW_SMS_DEBUG_ENDPOINT"
            ),
        }
    )
    if sms_violation:
        if mode == "strict":
            report.weak_secrets.append(f"SMS_DEBUG_ENABLED ({sms_violation})")
        else:
            report.warnings.append(sms_violation)

    # 小程序码 env_version:develop/非法值在 strict 下是硬错误,trial 只警告
    miniprogram_env = {
        "WECHAT_MINIPROGRAM_ENV_VERSION": _effective(
            settings, file_vars, "WECHAT_MINIPROGRAM_ENV_VERSION"
        ),
    }
    miniprogram_violation = _miniprogram_env_violation(miniprogram_env)
    if miniprogram_violation:
        if mode == "strict":
            report.weak_secrets.append(
                f"MINIPROGRAM_ENV_VERSION ({miniprogram_violation})"
            )
        else:
            report.warnings.append(miniprogram_violation)
    miniprogram_warning = _miniprogram_env_warning(miniprogram_env)
    if miniprogram_warning:
        report.warnings.append(miniprogram_warning)

    # 推荐变量缺失
    for key in RECOMMENDED:
        if not _effective(settings, file_vars, key):
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

    sms_violation = _sms_debug_violation(merged)
    if sms_violation:
        if mode == "strict":
            report.weak_secrets.append(f"SMS_DEBUG_ENABLED ({sms_violation})")
        else:
            report.warnings.append(sms_violation)

    miniprogram_violation = _miniprogram_env_violation(merged)
    if miniprogram_violation:
        if mode == "strict":
            report.weak_secrets.append(
                f"MINIPROGRAM_ENV_VERSION ({miniprogram_violation})"
            )
        else:
            report.warnings.append(miniprogram_violation)
    miniprogram_warning = _miniprogram_env_warning(merged)
    if miniprogram_warning:
        report.warnings.append(miniprogram_warning)

    for key in RECOMMENDED:
        if not _get(merged, key):
            report.warnings.append(f"RECOMMENDED var {key} not set")

    return report
