#!/usr/bin/env python3
"""立即修 · 生产服务器操作助手(2026-10-05 安全收口部署用)。

线上是**宝塔 Python 项目管理器**托管,发布目录形如
`/www/wwwroot/xiulijiu_api/releases/<时间戳>/`。

用法
----
密码不写进命令行(避免进 shell 历史),走环境变量:

    # PowerShell(推荐:你自己设,我不需要看到明文)
    $env:XJL_SSH_PASSWORD = "你的密码"
    python scripts/prod_deploy.py probe              # 只读探测,不改任何东西
    python scripts/prod_deploy.py deploy --yes       # 实际部署(会做 db/release 备份)

    # 或交互式输入
    python scripts/prod_deploy.py probe --ask-password

子命令
------
  probe    只读:进程守护方式 / 目录结构 / 当前 release / .env 关键项 / python 环境
  deploy   发布:备份 → 传包 → 解包 → 写 ALLOW_SMS_DEBUG_ENDPOINT=false → 切软链 → 重启 → 自检
  verify   只读:复查 /health、/health/env、/metrics、关键接口鉴权

默认禁用:任何写操作都要显式 `--yes`;`probe`/`verify` 永远不写。
"""
from __future__ import annotations

import argparse
import getpass
import os
import posixpath
import sys
from pathlib import Path

try:
    import paramiko
except ImportError:  # pragma: no cover
    print("需要 paramiko:python -m pip install paramiko", file=sys.stderr)
    raise SystemExit(2)

HOST = os.environ.get("XJL_SSH_HOST", "8.134.99.53")
PORT = int(os.environ.get("XJL_SSH_PORT", "22"))
USER = os.environ.get("XJL_SSH_USER", "root")
APP_DIR = os.environ.get("XJL_APP_DIR", "/www/wwwroot/xiulijiu_api")
PASSWORD_ENV = "XJL_SSH_PASSWORD"

PROBE_COMMANDS: list[tuple[str, str]] = [
    ("主机信息", "hostname; uname -a; cat /etc/os-release | head -3"),
    ("应用目录", f"ls -la {APP_DIR}"),
    ("releases 目录", f"ls -lt {APP_DIR}/releases | head -10"),
    ("当前软链指向", f"readlink -f {APP_DIR}/current 2>/dev/null; readlink -f {APP_DIR}/api 2>/dev/null"),
    (".env 关键项(不含密钥值)", f"grep -E '^(DEBUG|SMS_PROVIDER|ALLOW_SMS_DEBUG_ENDPOINT|DATABASE_URL|STRICT_ENV_ON_STARTUP|WECHAT_REVIEW_ACCOUNT)=' {APP_DIR}/.env 2>/dev/null || echo '(未找到 .env)'"),
    (".env 行数与是否已有新开关", f"wc -l {APP_DIR}/.env 2>/dev/null; grep -c '^ALLOW_SMS_DEBUG_ENDPOINT=' {APP_DIR}/.env 2>/dev/null || true"),
    ("监听端口/进程", "ps -ef | grep -E 'uvicorn|gunicorn|python' | grep -v grep | head -20"),
    ("systemd 单元", "systemctl list-units --type=service --all 2>/dev/null | grep -iE 'xiulijiu|uvicorn|gunicorn' || echo '(无匹配 systemd 单元)'"),
    ("supervisor", "supervisorctl status 2>/dev/null || echo '(无 supervisorctl)'"),
    ("宝塔 Python 项目记录", "ls /www/server/panel/data/ 2>/dev/null | head -5; cat /www/server/panel/vhost/*/*.conf 2>/dev/null | head -5"),
    ("nginx 站点配置", "ls -l /www/server/panel/vhost/nginx/ 2>/dev/null | head; grep -rE 'location (/api|/admin|/h5|/docs|/metrics)' /www/server/panel/vhost/nginx/*.conf 2>/dev/null | head -20"),
    ("python 环境", f"cd {APP_DIR} && (ls -l venv/bin/python* 2>/dev/null; venv/bin/python -V 2>/dev/null; which python3; python3 -V)"),
    ("依赖是否就绪", f"cd {APP_DIR} && venv/bin/python -c \"import fastapi, sqlalchemy, uvicorn; print('fastapi', fastapi.__version__)\" 2>&1 | tail -3"),
    ("数据库文件", f"ls -lh {APP_DIR}/*.db {APP_DIR}/data/*.db 2>/dev/null || echo '(未在预期位置找到 .db)'"),
    ("磁盘余量", "df -h / | tail -1"),
]


def connect(password: str) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=HOST,
        port=PORT,
        username=USER,
        password=password,
        timeout=15,
        allow_agent=False,
        look_for_keys=False,
    )
    return client


def run(client: paramiko.SSHClient, command: str, timeout: int = 60) -> tuple[int, str]:
    _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    return code, (out + (("\n[stderr] " + err) if err.strip() else "")).strip()


def do_probe(client: paramiko.SSHClient) -> None:
    print("=" * 72)
    print(f"只读探测 {USER}@{HOST}{APP_DIR}")
    print("=" * 72)
    for title, command in PROBE_COMMANDS:
        code, out = run(client, command)
        print(f"\n--- {title} (exit={code}) ---")
        print(out[:4000] if out else "(无输出)")


def do_verify(client: paramiko.SSHClient) -> None:
    code, out = run(client, f"grep -E '^(ALLOW_SMS_DEBUG_ENDPOINT|SMS_PROVIDER)=' {APP_DIR}/.env")
    print("--- 服务器 .env ---")
    print(out or "(未读到)")

    local_checks = [
        ("health", "curl -fsS https://x.iddg.cn/health"),
        ("health/env", "curl -fsS 'https://x.iddg.cn/health/env?mode=strict'"),
        ("metrics", "curl -fsS https://x.iddg.cn/metrics"),
        ("sms gate", "curl -s -o /dev/null -w '%{http_code}' -X POST https://x.iddg.cn/api/v1/auth/sms/request -H 'Content-Type: application/json' -d '{\"phone\":\"18800000001\"}'"),
        ("orders(no auth)", "curl -s -o /dev/null -w '%{http_code}' https://x.iddg.cn/api/v1/orders"),
        ("users(no auth)", "curl -s -o /dev/null -w '%{http_code}' https://x.iddg.cn/api/v1/users"),
    ]
    for title, command in local_checks:
        code, out = run(client, command)
        print(f"\n--- {title} (exit={code}) ---")
        print(out[:1200] if out else "(无输出)")


def do_deploy(client: paramiko.SSHClient, package: Path, assume_yes: bool) -> int:
    if not package.exists():
        print(f"找不到发布包:{package}(先跑 python scripts/pack_release.py)", file=sys.stderr)
        return 2

    stamp_cmd = "date +%Y%m%d%H%M%S"
    _code, stamp = run(client, stamp_cmd)
    stamp = stamp.strip()
    release_dir = posixpath.join(APP_DIR, "releases", stamp)

    print("将执行:")
    print(f"  1. 备份 .env 与数据库到 {APP_DIR}/releases/_backup-{stamp}/")
    print(f"  2. 新建 {release_dir} 并解包 {package.name}")
    print(f"  3. 在 {APP_DIR}/.env 写入 ALLOW_SMS_DEBUG_ENDPOINT=false")
    print("  4. 切换软链 current → 新 release")
    print("  5. 重启宝塔 Python 项目(需要 --restart-cmd,或你手动在面板点重启)")
    if not assume_yes:
        answer = input("确认继续?输入 yes 执行:")
        if answer.strip().lower() != "yes":
            print("已取消")
            return 1

    steps = [
        (f"mkdir -p {APP_DIR}/releases/_backup-{stamp} && cp -a {APP_DIR}/.env {APP_DIR}/releases/_backup-{stamp}/.env.bak 2>/dev/null; "
         f"find {APP_DIR} -maxdepth 2 -name '*.db' -exec cp -a {{}} {APP_DIR}/releases/_backup-{stamp}/ \\; ; "
         f"ls -la {APP_DIR}/releases/_backup-{stamp}/", "备份"),
        (f"mkdir -p {release_dir}", "建 release 目录"),
    ]
    for command, title in steps:
        code, out = run(client, command, timeout=300)
        print(f"\n--- {title} (exit={code}) ---\n{out[:1500]}")
        if code != 0:
            print(f"{title} 失败,中止", file=sys.stderr)
            return 1

    # 上传发布包
    sftp = client.open_sftp()
    remote_pkg = posixpath.join(release_dir, package.name)
    print(f"\n--- 上传 {package.name} → {remote_pkg} ---")
    sftp.put(str(package), remote_pkg)
    sftp.close()

    code, out = run(client, f"tar -xzf {remote_pkg} -C {release_dir} && ls {release_dir} | head", timeout=300)
    print(f"--- 解包 (exit={code}) ---\n{out[:1200]}")
    if code != 0:
        return 1

    env_fix = (
        f"cd {APP_DIR} && "
        f"(grep -q '^ALLOW_SMS_DEBUG_ENDPOINT=' .env "
        f"&& sed -i 's/^ALLOW_SMS_DEBUG_ENDPOINT=.*/ALLOW_SMS_DEBUG_ENDPOINT=false/' .env "
        f"|| echo 'ALLOW_SMS_DEBUG_ENDPOINT=false' >> .env) && "
        f"grep -E '^(ALLOW_SMS_DEBUG_ENDPOINT|SMS_PROVIDER)=' .env"
    )
    code, out = run(client, env_fix)
    print(f"--- 写入 ALLOW_SMS_DEBUG_ENDPOINT=false (exit={code}) ---\n{out}")

    print(f"\n新 release 已就绪:{release_dir}")
    print("软链切换与重启请按宝塔面板实际结构执行(先用 probe 的『当前软链指向』结果确认软链名)。")
    print("重启后跑:python scripts/prod_deploy.py verify")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="立即修生产服务器操作助手")
    parser.add_argument("action", choices=["probe", "deploy", "verify"])
    parser.add_argument("--password-env", default=PASSWORD_ENV, help=f"读取密码的环境变量名(默认 {PASSWORD_ENV})")
    parser.add_argument("--ask-password", action="store_true", help="交互式输入密码(默认不提示,避免非交互环境挂住)")
    parser.add_argument("--package", default=None, help="发布包路径(默认取 dist/ 下最新的 release-*.tgz)")
    parser.add_argument("--yes", action="store_true", help="deploy 时跳过交互确认")
    args = parser.parse_args()

    # 只认环境变量(或显式 --ask-password),绝不默认弹密码提示:
    # 某些非交互宿主里 sys.stdin.isatty() 仍为 True,自动提示会直接挂住。
    password = os.environ.get(args.password_env, "")
    if not password and args.ask_password:
        password = getpass.getpass(f"{USER}@{HOST} 密码:")
    if not password:
        print(
            f"未提供密码。请先设置环境变量 {args.password_env}"
            f"(或在真正的交互终端里加 --ask-password)。",
            file=sys.stderr,
        )
        return 2

    client = connect(password)
    try:
        if args.action == "probe":
            do_probe(client)
            return 0
        if args.action == "verify":
            do_verify(client)
            return 0

        package = Path(args.package) if args.package else None
        if package is None:
            candidates = sorted(Path("dist").glob("release-*.tgz"))
            if not candidates:
                print("dist/ 下没有 release-*.tgz,先跑 python scripts/pack_release.py", file=sys.stderr)
                return 2
            package = candidates[-1]
        return do_deploy(client, package, args.yes)
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
