#!/usr/bin/env python3
"""立即修 · 线上区域清理工具(只读探测 / 在线备份 / 事务删除)。

背景
----
线上是宝塔托管的 FastAPI + SQLite。`regions` 表被 6 张表外键引用,而且后端
**没有** DELETE /api/v1/regions/{id} 接口,`RegionUpdate` 也只放开 name/manager_id,
所以层级(level)、上级(parent_id)建错的记录在后台里永远修不好 —— 只能直接动库。

安全设计(重要)
--------------
  * probe / backup 永远只读,不写任何东西
  * apply 先做一次 SQLite 在线备份(backup API,不锁库、不拷贝半个文件),再开始写
  * apply 对每个待删 id 逐条检查 7 处引用;任何一处非 0 就**拒绝**该条(除非 --force)
  * 所有删除在单个事务里完成,异常自动 ROLLBACK

用法
----
    # 密码走环境变量,别写进命令行(避免进 shell 历史)
    $env:XJL_SSH_PASSWORD = "..."

    python scripts/prod_region_cleanup.py probe                 # 只读:区域 + 引用计数 + 门店
    python scripts/prod_region_cleanup.py backup                # 只读:线上库在线备份
    python scripts/prod_region_cleanup.py apply --delete 5,6    # 预演(默认不写)
    python scripts/prod_region_cleanup.py apply --delete 5,6 --yes   # 真删

环境变量(与 scripts/prod_deploy.py 一致):
    XJL_SSH_HOST  默认 8.134.99.53
    XJL_SSH_PORT  默认 22
    XJL_SSH_USER  默认 root
    XJL_APP_DIR   默认 /www/wwwroot/xiulijiu_api
    XJL_SSH_PASSWORD  必填
"""
from __future__ import annotations

import argparse
import json
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

REMOTE_TOOL = "/tmp/xjl_region_tool.py"

# --------------------------------------------------------------------------
# 服务端脚本:上传到服务器后用服务器自己的 python 执行,避免引号地狱
# --------------------------------------------------------------------------
SERVER_TOOL = r'''
import hashlib, json, os, shutil, sqlite3, sys, datetime

REF_TABLES = [
    ("stores", "region_id"),
    ("store_addresses", "region_id"),
    ("orders", "region_id"),
    ("customer_addresses", "region_id"),
    ("domestic_demands", "region_id"),
    ("repairers", "region_id"),
    ("regions", "parent_id"),
]


def table_exists(con, name):
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def refs(con, rid):
    out = {}
    for table, col in REF_TABLES:
        if not table_exists(con, table):
            continue
        n = con.execute(
            "SELECT COUNT(*) FROM %s WHERE %s = ?" % (table, col), (rid,)
        ).fetchone()[0]
        if n:
            out["%s.%s" % (table, col)] = n
    return out


def dump_regions(con):
    rows = con.execute(
        "SELECT id, name, level, parent_id, manager_id FROM regions ORDER BY id"
    ).fetchall()
    out = []
    for rid, name, level, parent_id, manager_id in rows:
        out.append({
            "id": rid, "name": name, "level": level,
            "parent_id": parent_id, "manager_id": manager_id,
            "refs": refs(con, rid),
        })
    return out


def dump_stores(con):
    if not table_exists(con, "stores"):
        return []
    rows = con.execute(
        "SELECT id, name, region_id, manager_id, enabled, status FROM stores ORDER BY id"
    ).fetchall()
    return [
        {"id": r[0], "name": r[1], "region_id": r[2], "manager_id": r[3],
         "enabled": bool(r[4]), "status": r[5]}
        for r in rows
    ]


def cmd_probe(db):
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    print(json.dumps({
        "db": db,
        "db_size": os.path.getsize(db),
        "regions": dump_regions(con),
        "stores": dump_stores(con),
    }, ensure_ascii=False, indent=2))
    con.close()


def cmd_backup(db):
    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    bak = "%s.bak-%s" % (db, stamp)
    src = sqlite3.connect(db)
    dst = sqlite3.connect(bak)
    with dst:
        src.backup(dst)          # 在线备份:不需要停服务
    dst.close()
    src.close()
    h = hashlib.sha256()
    with open(bak, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    print(json.dumps({
        "backup": bak, "bytes": os.path.getsize(bak),
        "sha256": h.hexdigest(), "source_bytes": os.path.getsize(db),
    }, ensure_ascii=False, indent=2))


def cmd_apply(db, ids, force, yes):
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=ON")
    con.isolation_level = None
    plan, blocked = [], []

    for rid in ids:
        row = con.execute(
            "SELECT id, name, level, parent_id FROM regions WHERE id=?", (rid,)
        ).fetchone()
        if row is None:
            blocked.append({"id": rid, "reason": "region not found"})
            continue
        r = refs(con, rid)
        item = {"id": row[0], "name": row[1], "level": row[2],
                "parent_id": row[3], "refs": r}
        if r and not force:
            item["reason"] = "被引用,拒绝删除(加 --force 可强制)"
            blocked.append(item)
        else:
            plan.append(item)

    result = {"db": db, "would_delete": plan, "blocked": blocked, "executed": False}

    if not plan:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        con.close()
        return 1 if blocked else 0

    if not yes:
        result["note"] = "预演模式,未写入。加 --yes 才会真删。"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        con.close()
        return 0

    cur = con.cursor()
    cur.execute("BEGIN IMMEDIATE")
    try:
        for item in plan:
            cur.execute("DELETE FROM regions WHERE id=?", (item["id"],))
        cur.execute("COMMIT")
    except Exception as exc:                      # noqa: BLE001
        cur.execute("ROLLBACK")
        result["error"] = repr(exc)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        con.close()
        return 2

    result["executed"] = True
    result["regions_after"] = dump_regions(con)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    con.close()
    return 0


if __name__ == "__main__":
    mode = sys.argv[1]
    db = sys.argv[2]
    if mode == "probe":
        cmd_probe(db)
    elif mode == "backup":
        cmd_backup(db)
    elif mode == "apply":
        ids = [int(x) for x in sys.argv[3].split(",") if x.strip()]
        force = "--force" in sys.argv
        yes = "--yes" in sys.argv
        sys.exit(cmd_apply(db, ids, force, yes))
    else:
        print("unknown mode", file=sys.stderr)
        sys.exit(2)
'''


# --------------------------------------------------------------------------
# 本地驱动
# --------------------------------------------------------------------------
def password() -> str:
    """优先环境变量,其次本地 .env(已 gitignore),最后交互输入。"""
    pw = os.environ.get(PASSWORD_ENV)
    if pw:
        return pw

    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith(f"{PASSWORD_ENV}="):
                pw = line.split("=", 1)[1].strip().strip('"').strip("'")
                if pw:
                    return pw

    import getpass

    pw = getpass.getpass(f"{USER}@{HOST} 密码:")
    if not pw:
        print(
            f"缺少 {PASSWORD_ENV}:请设置环境变量,或在 {env_file} 里加一行 "
            f"{PASSWORD_ENV}=你的密码",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return pw


def connect(pw: str) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=HOST, port=PORT, username=USER, password=pw,
        timeout=20, allow_agent=False, look_for_keys=False,
    )
    return client


def run(client: paramiko.SSHClient, command: str, timeout: int = 120) -> tuple[int, str]:
    _in, out, err = client.exec_command(command, timeout=timeout)
    o = out.read().decode("utf-8", "replace")
    e = err.read().decode("utf-8", "replace")
    return out.channel.recv_exit_status(), (o + (("\n[stderr] " + e) if e.strip() else "")).strip()


def upload_tool(client: paramiko.SSHClient) -> None:
    sftp = client.open_sftp()
    with sftp.file(REMOTE_TOOL, "w") as fh:
        fh.write(SERVER_TOOL)
    sftp.close()


def discover_python(client: paramiko.SSHClient) -> str:
    for candidate in (
        f"{APP_DIR}/venv/bin/python",
        f"{APP_DIR}/current/venv/bin/python",
        "python3",
    ):
        code, _ = run(client, f"test -x {candidate} && echo ok")
        if code == 0:
            return candidate
    return "python3"


def discover_db(client: paramiko.SSHClient) -> str:
    """优先用 DATABASE_URL,否则找最大的 .db 文件(排除 .bak-*)。"""
    code, out = run(
        client,
        f"grep -E '^DATABASE_URL=' {APP_DIR}/.env 2>/dev/null | head -1",
    )
    url = out.split("=", 1)[1].strip() if code == 0 and "=" in out else ""
    if url.startswith("sqlite"):
        rel = url.split("///", 1)[-1]
        if rel.startswith("./"):
            rel = rel[2:]
        if not rel.startswith("/"):
            for base in (APP_DIR, f"{APP_DIR}/current"):
                cand = posixpath.join(base, rel)
                c2, _ = run(client, f"test -f {cand} && echo ok")
                if c2 == 0:
                    return cand

    code, out = run(
        client,
        f"find {APP_DIR} -maxdepth 3 -name '*.db' -not -name '*.bak-*' "
        f"-printf '%s %p\\n' 2>/dev/null | sort -rn | head -5",
    )
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if not lines:
        print("在服务器上找不到 .db 文件,请用 --db 指定", file=sys.stderr)
        raise SystemExit(2)
    if len(lines) > 1:
        print("发现多个 .db,选最大的那个(可用 --db 覆盖):")
        for ln in lines:
            print("   ", ln)
    return lines[0].split(" ", 1)[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="线上区域清理(只读探测/备份/事务删除)")
    ap.add_argument("mode", choices=["probe", "backup", "apply"])
    ap.add_argument("--delete", help="apply 模式:要删除的区域 ID,逗号分隔,如 5,6")
    ap.add_argument("--force", action="store_true", help="忽略引用检查(危险)")
    ap.add_argument("--yes", action="store_true", help="真正执行写入(默认只预演)")
    ap.add_argument("--db", help="手动指定线上 sqlite 文件绝对路径")
    args = ap.parse_args()

    if args.mode == "apply" and not args.delete:
        print("apply 模式必须给 --delete 5,6", file=sys.stderr)
        return 2

    client = connect(password())
    try:
        upload_tool(client)
        py = discover_python(client)
        db = args.db or discover_db(client)
        print(f"# host={HOST} app_dir={APP_DIR}\n# python={py}\n# db={db}\n")

        if args.mode == "probe":
            _, out = run(client, f"{py} {REMOTE_TOOL} probe {db}")
            print(out)
            return 0

        if args.mode == "backup":
            _, out = run(client, f"{py} {REMOTE_TOOL} backup {db}", timeout=300)
            print(out)
            return 0

        # apply:先强制备份,再写
        print("--- 1) 删除前强制备份 ---")
        _, out = run(client, f"{py} {REMOTE_TOOL} backup {db}", timeout=300)
        print(out)
        if '"backup"' not in out:
            print("备份失败,中止", file=sys.stderr)
            return 2

        print("\n--- 2) 预演 / 执行 ---")
        extra = " --force" if args.force else ""
        extra += " --yes" if args.yes else ""
        code, out = run(client, f"{py} {REMOTE_TOOL} apply {db} {args.delete}{extra}")
        print(out)
        return code
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
