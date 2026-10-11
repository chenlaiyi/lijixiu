#!/usr/bin/env python3
"""让 miniprogram-ci 兼容 Node 25 的内置 `global.localStorage`。

问题
----
Node 25 起 `globalThis.localStorage` 成为内置对象(未提供 `--localstorage-file`
时只有存储后端,没有 `getItem`)。而 miniprogram-ci(实测 2.1.31)的
`dist/utils/debug.js` 里三处写成:

    global.localStorage.getItem("inspectCompiler")
    global.localStorage.getItem("compilerInMainProcess")
    global.localStorage.getItem("compilerNotInWorker")

只要 `global.localStorage` 存在就会走这个分支,于是抛
`TypeError: r.getItem is not a function`,**编译子进程**同样会踩到,
表现为 `npm run upload` 直接失败:

    child process stdout: TypeError: r.getItem is not a function
        at shouldRunInMainProcess (miniprogram-ci/dist/utils/debug.js:1:755)

修复
----
把三处改成 `typeof r.getItem === "function" && r.getItem("X")`,语义等价,
但在没有 getItem 时安全短路(回落到 `process.versions.electron` 判定,
Node 下为 false → 在主进程编译)。

用法
----
    python scripts/patch_miniprogram_ci.py          # 打补丁(幂等)
    python scripts/patch_miniprogram_ci.py --check  # 只检查,不打补丁

`npm install` 会通过 package.json 的 postinstall 自动调用本脚本,所以正常情况下
不需要手动跑。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

TARGET = Path("node_modules/miniprogram-ci/dist/utils/debug.js")
KEYS = ("inspectCompiler", "compilerInMainProcess", "compilerNotInWorker")
MARKER = 'typeof r.getItem==="function"'


def apply_patch(target: Path) -> int:
    src = target.read_text(encoding="utf-8")
    if MARKER in src:
        print(f"已打过补丁:{target}")
        return 0

    patched = 0
    for key in KEYS:
        old = f'r.getItem("{key}")'
        if old not in src:
            continue
        src = src.replace(old, f'(typeof r.getItem==="function"&&r.getItem("{key}"))')
        patched += 1

    if patched == 0:
        print(f"未找到需要修改的调用点:{target}", file=sys.stderr)
        print("可能是 miniprogram-ci 版本已变更,请检查 dist/utils/debug.js。", file=sys.stderr)
        return 1

    target.write_text(src, encoding="utf-8", newline="")
    print(f"已 patch {patched} 处:{target}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="修补 miniprogram-ci 的 Node 25 localStorage 兼容问题")
    parser.add_argument("--check", action="store_true", help="只检查是否已打补丁,不修改文件")
    args = parser.parse_args()

    if not TARGET.exists():
        print(f"找不到 {TARGET};先运行 npm install。", file=sys.stderr)
        # postinstall 场景下 package-lock 里没有 miniprogram-ci 时不算失败
        return 0

    if args.check:
        src = TARGET.read_text(encoding="utf-8")
        if MARKER in src:
            print("OK: miniprogram-ci 已打好 Node 25 兼容补丁")
            return 0
        print("NEED PATCH: miniprogram-ci 尚未打补丁", file=sys.stderr)
        return 1

    return apply_patch(TARGET)


if __name__ == "__main__":
    raise SystemExit(main())
