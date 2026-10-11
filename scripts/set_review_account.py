"""生成微信审核账号密码并写入 .env(2026-10-05)。

用途:微信提审时审核人员走「账号密码登录」入口
(`POST /api/v1/auth/review-login`,账号 `reviewer`)。

行为:
- 生成 16 位强随机密码(大小写+数字+符号)
- 把 WECHAT_REVIEW_ACCOUNT / WECHAT_REVIEW_PASSWORD 写入指定 .env
  (已存在则原位替换,保留其余行;文件按 UTF-8 读写)
- 默认同时写入 WECHAT_REVIEW_PHONE=18800000999(如未设置)
- 打印密码供人工记录,并提示重启服务

用法:
    python scripts/set_review_account.py                  # 写 ./.env
    python scripts/set_review_account.py --env .env.prod  # 写指定文件
    python scripts/set_review_account.py --account auditor --dry-run
"""
from __future__ import annotations

import argparse
import secrets
import string
import sys
from pathlib import Path

ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*"
KEYS = ("WECHAT_REVIEW_ACCOUNT", "WECHAT_REVIEW_PASSWORD", "WECHAT_REVIEW_PHONE")
DEFAULT_PHONE = "18800000999"


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
    parser = argparse.ArgumentParser(description="生成/写入微信审核账号密码")
    parser.add_argument("--env", default=".env", help="目标 .env 路径(默认 ./.env)")
    parser.add_argument("--account", default="reviewer", help="审核账号名(默认 reviewer)")
    parser.add_argument("--phone", default=DEFAULT_PHONE, help="审核手机号(需在白名单内)")
    parser.add_argument("--length", type=int, default=16, help="密码长度(默认 16)")
    parser.add_argument("--dry-run", action="store_true", help="只打印,不写文件")
    args = parser.parse_args()

    path = Path(args.env)
    password = generate_password(args.length)
    updates = {
        "WECHAT_REVIEW_ACCOUNT": args.account,
        "WECHAT_REVIEW_PASSWORD": password,
        "WECHAT_REVIEW_PHONE": args.phone,
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
    print("  审核账号:", updates["WECHAT_REVIEW_ACCOUNT"])
    print("  审核密码:", password)
    print("  审核手机:", updates["WECHAT_REVIEW_PHONE"])
    print()
    print("下一步:")
    print("  1. 重启后端服务(settings 在启动时读取 .env)")
    print("  2. python scripts/validate_env.py 确认没有新增告警")
    print("  3. 用 POST /api/v1/auth/review-login 验证:account/password")
    print()
    print("注意:密码只显示这一次,请立即记录到密码管理器。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
