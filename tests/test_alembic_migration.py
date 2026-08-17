"""alembic 迁移端到端测试(2026-08-09)。

验证:
  - alembic upgrade head 能成功建所有表
  - alembic downgrade base 能回滚
  - 关键表都存在
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"


def run(cmd, env=None, cwd=None):
    """跑子进程,捕获输出。"""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    r = subprocess.run(
        cmd, capture_output=True, text=True, env=full_env, cwd=cwd or str(PROJECT_ROOT)
    )
    return r.returncode, r.stdout, r.stderr


def main():
    results = []
    def check(name, ok, detail=""):
        results.append((name, ok, detail))
        print(("OK  " if ok else "FAIL") + f" {name:48s} {detail}")

    # 准备临时 sqlite db
    tmp = tempfile.NamedTemporaryFile(prefix="alembic_test_", suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    print(f"test db: {db_path}")

    try:
        # 1) upgrade head
        rc, out, err = run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            env={"DATABASE_URL": f"sqlite:///{db_path}"},
        )
        check("alembic-upgrade-head", rc == 0, f"rc={rc}")
        if rc != 0:
            print("STDOUT:", out[-500:])
            print("STDERR:", err[-500:])

        # 2) 验证表
        import sqlite3
        conn = sqlite3.connect(db_path)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alembic_%'").fetchall()]
        conn.close()
        check("tables-count-geq-30", len(tables) >= 30, f"got {len(tables)}")
        must_have = [
            "users", "orders", "wallets", "ledgers", "withdrawals",
            "alert_events", "service_bills", "profit_shares",
            "service_areas", "reconciliation_logs", "pay_orders",
            "refund_orders", "stores", "regions", "repairers",
        ]
        for t in must_have:
            check(f"table-{t}", t in tables)

        # 3) idempotent 跑第二次
        rc2, _, _ = run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            env={"DATABASE_URL": f"sqlite:///{db_path}"},
        )
        check("alembic-upgrade-idempotent", rc2 == 0, f"rc={rc2}")

        # 4) downgrade base
        rc3, out3, err3 = run(
            [sys.executable, "-m", "alembic", "downgrade", "base"],
            env={"DATABASE_URL": f"sqlite:///{db_path}"},
        )
        check("alembic-downgrade-base", rc3 == 0, f"rc={rc3}")
        if rc3 != 0:
            print("STDERR:", err3[-500:])

        # 5) 验证回滚后表没了
        conn = sqlite3.connect(db_path)
        remaining = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
        conn.close()
        # alembic_version 表还在(其他业务表都没了)
        business_tables = [t for t in remaining if t != "alembic_version"]
        check("downgrade-removed-business-tables", len(business_tables) == 0, f"remaining={business_tables}")

        # 6) 重新 upgrade(回滚后)
        rc4, _, _ = run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            env={"DATABASE_URL": f"sqlite:///{db_path}"},
        )
        check("alembic-upgrade-after-downgrade", rc4 == 0, f"rc={rc4}")

        conn = sqlite3.connect(db_path)
        tables2 = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alembic_%'").fetchall()]
        conn.close()
        check("upgrade-restored-all-tables", len(tables2) == len(tables), f"before={len(tables)} after={len(tables2)}")

    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass

    # summary
    print("---")
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
