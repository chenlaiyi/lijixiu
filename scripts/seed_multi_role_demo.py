"""把一个手机号配置成多角色账号(店长 + 师傅 + 业务)。

用法:
    python scripts/seed_multi_role_demo.py 18060936373
    python scripts/seed_multi_role_demo.py 18060936373 --roles store_manager,repairer,promotion_manager
    python scripts/seed_multi_role_demo.py 18060936373 --dry-run

设计取舍:
  * 直接写库(SQLAlchemy),不走 HTTP —— 建号本身需要平台管理员 token,
    运维脚本不该依赖「先有人登录后台」。
  * 走 app.services.role.set_roles,所以角色集合、兼容字段(business_role /
    role / is_promotion_manager)和 user_role_grants 审计三者一起更新,
    和后台「配置角色」按钮是同一条代码路径。
  * 幂等:重复执行只会补齐缺失的角色,不会清掉后台后来加的角色(除非显式传
    --replace)。

环境变量 DATABASE_URL 决定落在哪个库(默认与 .env 一致)。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.database import async_session, init_db  # noqa: E402
from app.models.user import BusinessRole, User, normalize_business_roles  # noqa: E402
from app.services import role as role_service  # noqa: E402

DEFAULT_ROLES = [
    BusinessRole.STORE_MANAGER.value,
    BusinessRole.REPAIRER.value,
    BusinessRole.PROMOTION_MANAGER.value,
]

DEFAULT_NAMES = {
    BusinessRole.STORE_MANAGER.value: "多角色演示(店长+师傅+业务)",
}


async def seed(phone: str, roles: list[str], name: str | None, replace: bool, dry_run: bool) -> int:
    await init_db()
    async with async_session() as db:
        user = (
            await db.execute(select(User).where(User.phone == phone))
        ).scalar_one_or_none()

        wanted = normalize_business_roles(roles)
        if not wanted:
            print(f"[x] 角色不合法:{roles}")
            print(f"    可用:{', '.join(item.value for item in BusinessRole)}")
            return 2

        if user is None:
            if dry_run:
                print(f"[dry-run] 会新建账号 {phone},角色 {wanted}")
                return 0
            user = User(
                phone=phone,
                name=name or DEFAULT_NAMES.get(wanted[0], f"多角色用户{phone[-4:]}"),
                business_roles=wanted,
                active_business_role=wanted[0],
                business_role=wanted[0],
            )
            role_service.sync_legacy_business_role(user, wanted)
            db.add(user)
            await db.flush()
            print(f"[+] 新建账号 #{user.id} {phone} -> {wanted}")
        else:
            before = role_service.resolve_roles(user)
            target = wanted if replace else normalize_business_roles([*before, *wanted])
            if before == target:
                print(f"[=] 账号 #{user.id} {phone} 角色已经是 {before},无需变更")
                return 0
            if name:
                user.name = name
            if dry_run:
                print(f"[dry-run] 账号 #{user.id} {phone}:{before} -> {target}")
                return 0
            roles_now, granted, revoked = await role_service.set_roles(
                db, user, target, source="system", remark="seed_multi_role_demo"
            )
            print(
                f"[~] 账号 #{user.id} {phone}:{before} -> {roles_now}"
                f"(新增 {granted or '无'},收回 {revoked or '无'})"
            )

        await db.commit()
        await db.refresh(user)
        print(
            f"[ok] #{user.id} {user.phone} {user.name} "
            f"角色={role_service.resolve_roles(user)} "
            f"当前身份={role_service.active_role(user)}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="配置多角色演示账号")
    parser.add_argument("phone", help="手机号,如 18060936373")
    parser.add_argument(
        "--roles",
        default=",".join(DEFAULT_ROLES),
        help=f"逗号分隔的业务角色,默认 {','.join(DEFAULT_ROLES)}",
    )
    parser.add_argument("--name", default=None, help="账号姓名(仅新建或显式传入时生效)")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="用给定角色整体替换(默认只做补齐,不删除已有角色)",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印将要做的变更")
    args = parser.parse_args()

    roles = [item.strip() for item in args.roles.split(",") if item.strip()]
    return asyncio.run(seed(args.phone.strip(), roles, args.name, args.replace, args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
