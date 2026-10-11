"""生成管理后台账号密码并写入 .env(2026-10-07)。

用途:管理后台(https://x.iddg.cn/admin/)不再需要手工粘贴 token,
改为在登录框填「账号 + 密码」。本脚本生成凭据并写入 .env。

对应接口:`POST /api/v1/auth/admin-login`
  body: {"account": "...", "password": "..."} → {"token": "...", "user": {...}}

写入的键:
  ADMIN_WEB_ACCOUNT   账号(默认 admin)
  ADMIN_WEB_PASSWORD  密码(默认生成 16 位强随机)
  ADMIN_WEB_PHONE     登录后映射到的用户手机号,必须在演示白名单内
                      且该手机号的角色是 platform_admin(默认 18800000000)

用法:
    python scripts/set_admin_account.py                     # 写 ./.env
    python scripts/set_admin_account.py --env .env.prod     # 写指定文件
    python scripts/set_admin_account.py --account ops --password 'MyPass123!'
    python scripts/set_admin_account.py --dry-run
"""
from __future__ import annotations

import argparse
import secrets
import string
import sys
from pathlib import Path

ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*"
DEFAULT_PHONE = "18800000000"  # app/routers/auth.py::_DEMO_ACCOUNTS 里的 platform_admin


def generate_password(length: int = 16) -> str:
    """保证至少各含一个大写、小写、数字、符号。"""
    while True:
        pwd = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if (
            any(c.islower() for c in pwd)
            and any(c.isupper() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in "!@#$%^&*" for c in pwd)
        ):
            return pwd


def upsert(text: str, updates: dict[str, str]) -> str:
    lines = text.splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成/写入管理后台账号密码")
    parser.add_argument("--env", default=".env", help="目标 .env 路径(默认 ./.env)")
    parser.add_argument("--account", default="admin", help="后台账号名(默认 admin)")
    parser.add_argument("--password", default=None, help="指定密码(不传则随机生成)")
    parser.add_argument("--phone", default=DEFAULT_PHONE, help="映射到的用户手机号(需为平台管理员)")
    parser.add_argument("--length", type=int, default=16, help="随机密码长度(默认 16)")
    parser.add_argument("--dry-run", action="store_true", help="只打印,不写文件")
    args = parser.parse_args()

    path = Path(args.env)
    password = args.password or generate_password(args.length)
    if args.password and len(args.password) < 8:
        print("密码至少 8 位", file=sys.stderr)
        return 1
    updates = {
        "ADMIN_WEB_ACCOUNT": args.account,
        "ADMIN_WEB_PASSWORD": password,
        "ADMIN_WEB_PHONE": args.phone,
    }

    if args.dry_run:
        print("[dry-run] 将要写入", path)
        for key, value in updates.items():
            print(f"  {key}={value}")
        return 0

    if not path.exists():
        print(f"目标文件不存在:{path}", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8")
    path.write_text(upsert(text, updates), encoding="utf-8")

    print(f"已写入 {path}")
    print("  后台账号:", updates["ADMIN_WEB_ACCOUNT"])
    print("  后台密码:", password)
    print("  映射手机:", updates["ADMIN_WEB_PHONE"])
    print()
    print("下一步:")
    print("  1. 重启后端服务(settings 在启动时读取 .env)")
    print("  2. 打开 https://x.iddg.cn/admin/ ,用上面的账号密码登录")
    print("  3. 如页面提示「后台登录未配置」,说明 1 还没生效")
    print()
    print("注意:修改 ADMIN_WEB_PASSWORD 不会作废已发出的 token;")
    print("      要作废需更换 AUTH_SECRET 并重启。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
