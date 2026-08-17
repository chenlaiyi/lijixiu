#!/usr/bin/env python
"""
validate_env.py — Pre-flight check for .env completeness.

CLI wrapper around app.core.env_validator. Use this from the shell, deploy.sh, and CI.

Usage:
    python scripts/validate_env.py            # dev mode (lenient)
    python scripts/validate_env.py --strict   # prod mode (strict)
    python scripts/validate_env.py --prod     # alias for --strict
    python scripts/validate_env.py --json     # machine-readable output

Exit codes:
    0  — all required vars set
    1  — one or more required vars missing or placeholder (in strict mode)
    2  — .env file not found
    3  — weak AUTH_SECRET (strict mode only)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable


# 让 scripts/ 也能 import app.core.env_validator
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.env_validator import validate_from_environ, EnvReport  # noqa: E402


def _print_human(report: EnvReport) -> None:
    print(f"=== validate_env ({report.mode} mode) ===")
    print(f"env file: {report.found_path or '(not found)'}")
    if report.missing:
        print("\nMissing required keys:")
        for k in report.missing:
            print(f"  X {k}")
    if report.placeholders:
        suffix = " — will fail in strict mode" if report.mode == "dev" else ""
        print(f"\nPlaceholder keys (FILL_* / change-me){suffix}:")
        for k in report.placeholders:
            print(f"  ! {k}")
    if report.weak_secrets:
        print("\nWeak secrets:")
        for k in report.weak_secrets:
            print(f"  X {k}")
    if report.warnings:
        print("\nWarnings:")
        for w in report.warnings:
            print(f"  - {w}")
    print()
    if report.ok:
        print(f"OK — {len(report.warnings)} warning(s), 0 errors")
    else:
        print(f"FAIL — {len(report.errors)} error(s), {len(report.warnings)} warning(s)")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate .env for completeness and placeholder values",
    )
    parser.add_argument(
        "--strict", "--prod", dest="strict", action="store_true",
        help="Enforce prod rules: all WeChat secrets filled, strong AUTH_SECRET",
    )
    parser.add_argument(
        "--env", dest="env_path", default=None,
        help="Path to .env file (default: auto-detect from cwd)",
    )
    parser.add_argument(
        "--json", dest="as_json", action="store_true",
        help="Emit machine-readable JSON",
    )
    args = parser.parse_args(argv)

    mode = "strict" if args.strict else "dev"
    env_path = Path(args.env_path) if args.env_path else None
    report = validate_from_environ(mode=mode, env_path=env_path)

    if args.as_json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_human(report)

    if not env_path and report.found_path is None:
        return 2
    if report.weak_secrets and mode == "strict":
        return 3
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
