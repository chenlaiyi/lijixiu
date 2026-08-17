"""分布式锁服务

提供 Redis 风格的分布式锁接口，当前 SQLite 实现，可替换为 Redis。

用法:
    lock = DistributedLock("lock:order:1", ttl=30)
    async with lock:
        # 临界区代码
"""

import asyncio
import time
import uuid
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import async_session


class LockTimeout(Exception):
    """获取锁超时"""
    pass


class DistributedLock:
    """Redis 风格分布式锁 — SQLite 实现

    生产环境替换 _acquire/_release 为 Redis SET NX / DEL 即可。
    """

    def __init__(self, key: str, ttl: int = 30, owner: str | None = None):
        self.key = f"dist_lock:{key}"
        self.ttl = ttl
        self.owner = owner or str(uuid.uuid4())[:8]
        self._acquired = False

    async def _acquire(self) -> bool:
        """尝试获取锁（SQLite 实现）"""
        try:
            async with async_session() as db:
                # 清理过期锁
                await db.execute(
                    text(
                        "DELETE FROM distributed_locks "
                        "WHERE key = :key AND expires_at < datetime('now')"
                    ),
                    {"key": self.key},
                )
                await db.commit()

                # 尝试插入
                try:
                    await db.execute(
                        text(
                            "INSERT INTO distributed_locks (key, owner, expires_at) "
                            "VALUES (:key, :owner, datetime('now', :ttl || ' seconds'))"
                        ),
                        {"key": self.key, "owner": self.owner, "ttl": str(self.ttl)},
                    )
                    await db.commit()
                    return True
                except Exception:
                    return False
        except Exception:
            return False

    async def _release(self):
        """释放锁"""
        try:
            async with async_session() as db:
                await db.execute(
                    text(
                        "DELETE FROM distributed_locks "
                        "WHERE key = :key AND owner = :owner"
                    ),
                    {"key": self.key, "owner": self.owner},
                )
                await db.commit()
        except Exception:
            pass

    async def acquire(self, timeout: float = 10.0) -> bool:
        """阻塞获取锁，直到成功或超时"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if await self._acquire():
                self._acquired = True
                return True
            await asyncio.sleep(0.1)
        return False

    async def release(self):
        if self._acquired:
            await self._release()
            self._acquired = False

    async def __aenter__(self):
        if not await self.acquire(timeout=self.ttl):
            raise LockTimeout(f"无法获取锁: {self.key}")
        return self

    async def __aexit__(self, *args):
        await self.release()


# 便捷工厂
def payment_lock(pay_order_id: int) -> DistributedLock:
    return DistributedLock(f"payment:callback:{pay_order_id}", ttl=30)


def wallet_lock(user_id: int) -> DistributedLock:
    return DistributedLock(f"wallet:update:{user_id}", ttl=10)


def profit_lock(order_id: int) -> DistributedLock:
    return DistributedLock(f"profit:calc:{order_id}", ttl=30)


def withdraw_lock(withdraw_id: int) -> DistributedLock:
    return DistributedLock(f"withdraw:{withdraw_id}", ttl=30)
