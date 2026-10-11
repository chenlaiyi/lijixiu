#!/usr/bin/env python3
"""把当前工作区打成可发布的后端 release 包。

线上是宝塔风格的 `releases/<时间戳>/` + 软链发布(从 `/health/env` 读到
`/www/wwwroot/xiulijiu_api/releases/20260818003556/.env`),所以只需要
一个「解包即用」的源码包 —— 不需要 docker 镜像。

用法
----
    python scripts/pack_release.py                  # 生成 dist/release-<时间戳>.tgz
    python scripts/pack_release.py --tag 20261005   # 自定义后缀
    python scripts/pack_release.py --no-verify      # 跳过本地自检

产出
----
    dist/release-<UTC时间戳>.tgz

包内容(app / h5 / admin-web / migrations / scripts / 依赖清单 / alembic 配置),
**不含** .env、cert/、xiulijiu.db、uploads/、node_modules/、.git/ —— 这些属于
服务器侧资产,部署时原样保留。

自检
----
默认会把生成的包解到临时目录,用 `DATABASE_URL=sqlite+aiosqlite:///<tmp>/probe.db`
导入 `app.main` 并初始化数据库,确认包内代码可直接运行。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

# 要打包的顶层条目(相对仓库根)
INCLUDE = [
    "app",
    "h5",
    "admin-web",
    "migrations",
    "scripts",
    "alembic.ini",
    "requirements.txt",
    "Dockerfile",
    "docker-compose.yml",
]

# 这些运行期资产必须留在服务器上,不进包
EXCLUDE_NAMES = {
    ".env", ".env.example", ".env.local",
    "cert", "xiulijiu.db", "uploads", ".git", "node_modules",
    "dist", "tests", "__pycache__", ".pytest_cache", ".venv",
    "miniprogram", "docs", "design", "._trash",
}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".db", ".db-shm", ".db-wal", ".log", ".tgz")


def iter_files():
    for name in INCLUDE:
        target = ROOT / name
        if not target.exists():
            print(f"  跳过(不存在):{name}", file=sys.stderr)
            continue
        if target.is_file():
            yield target
            continue
        for path in sorted(target.rglob("*")):
            if not path.is_file():
                continue
            parts = set(path.relative_to(ROOT).parts)
            if parts & EXCLUDE_NAMES:
                continue
            if path.suffix in EXCLUDE_SUFFIXES:
                continue
            if path.name in EXCLUDE_NAMES:
                continue
            yield path


def build(tag: str | None) -> Path:
    stamp = tag or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    DIST.mkdir(exist_ok=True)
    out = DIST / f"release-{stamp}.tgz"

    files = list(iter_files())
    with tarfile.open(out, "w:gz") as tar:
        for path in files:
            tar.add(path, arcname=str(path.relative_to(ROOT)), recursive=False)
    size_mb = out.stat().st_size / 1024 / 1024
    print(f"已生成 {out.relative_to(ROOT)}({len(files)} 个文件,{size_mb:.2f} MB)")
    return out


def verify(package: Path) -> int:
    """解包到临时目录,确认包内代码能 import 并初始化数据库。"""
    tmp = Path(tempfile.mkdtemp(prefix="xiulijiu-relcheck-"))
    try:
        with tarfile.open(package, "r:gz") as tar:
            tar.extractall(tmp)

        env = dict(os.environ)
        env["DATABASE_URL"] = f"sqlite+aiosqlite:///{(tmp / 'probe.db').as_posix()}"
        env["ALLOW_SMS_DEBUG_ENDPOINT"] = "false"
        env["PYTHONIOENCODING"] = "utf-8"

        code = (
            "import asyncio\n"
            "from app.core.database import init_db\n"
            "from app.main import app\n"
            "asyncio.run(init_db())\n"
            "print('release package import + init_db OK; routes =', len(app.routes))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=tmp,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            print("自检失败:", file=sys.stderr)
            print(result.stdout[-2000:], file=sys.stderr)
            print(result.stderr[-3000:], file=sys.stderr)
            return 1
        print("自检通过:", result.stdout.strip())
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="打包后端 release")
    parser.add_argument("--tag", default=None, help="自定义后缀(默认 UTC 时间戳)")
    parser.add_argument("--no-verify", action="store_true", help="跳过解包自检")
    args = parser.parse_args()

    package = build(args.tag)
    if not args.no_verify:
        rc = verify(package)
        if rc != 0:
            print("包自检未通过,已保留文件以便排查:", package, file=sys.stderr)
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
