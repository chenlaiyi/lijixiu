"""SQLAlchemy declarative base — 独立模块,避免 import database.py 触发 engine。

2026-08-09: 抽出,让 alembic env.py 能干净 import metadata。
2026-10-05: 新增 `enum_column()` —— 大小写不敏感的枚举列。
"""

import enum
from collections.abc import Mapping
from typing import Any, TypeVar

from sqlalchemy import Enum
from sqlalchemy.orm import DeclarativeBase

E = TypeVar("E", bound=enum.Enum)


class Base(DeclarativeBase):
    pass


class CaseInsensitiveEnum(Enum):
    """以枚举 `name`(大写)为落库规范形式,但读取时兼容历史小写值与旧枚举名。

    背景:SQLAlchemy 的 `Enum(PyEnum)` 默认按**枚举成员名**落库(`COMPLETED`),
    而业务代码/接口里到处用**枚举值**(`completed`)。历史上 seed 与部分服务
    直接写入小写值,导致:

      * `Order.status` 列里混有 `COMPLETED`(ORM 写)与 `completed`(raw SQL 写);
      * `SELECT ... WHERE status='completed'` 命中不到 `COMPLETED` → /metrics 恒为 0;
      * `profit_shares.role_type='PLATFORM'`(旧枚举名)读取时抛 LookupError → 500。

    该类型统一收口:

      * 写入:一律用 `.name`(大写),新数据不再产生歧义;
      * 读取:先按 `aliases` 映射历史名,再大小写归一化后解析;
      * 比较:`== "mismatch"` 这类字符串比较交给调用方改成枚举成员,类型本身
        不做魔法匹配。

    `aliases` 用于枚举成员被重命名/合并的历史值,例如旧代码写入的
    `TECHNICIAN_WAGE` 现在应解析为 `TECHNICIAN_WAGE`(同名)或
    `PLATFORM` → `PLATFORM_RETAINED`。
    """

    cache_ok = True

    def __init__(
        self,
        enum_class: type[enum.Enum] | None = None,
        *,
        aliases: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        self._aliases: dict[str, str] = {
            str(key).upper(): str(value).upper() for key, value in (aliases or {}).items()
        }
        if enum_class is None:
            # SQLAlchemy 在 adapt()/dialect_impl() 时会用 adapt(type(self)) 重建实例,
            # 这里允许无参构造,由 adapt() 复制原实例的属性。
            super().__init__(**kwargs)
            return
        kwargs.setdefault("values_callable", lambda cls: [member.name for member in cls])
        super().__init__(enum_class, **kwargs)

    def adapt(self, cls: type[Any], **kw: Any) -> Any:
        """派生新实例时带上 enum_class 与 aliases。

        默认实现会 `impltype(**kw)` 重建,而我们的构造签名第一个位置参数是
        枚举类,重建会直接 TypeError(已在本地复现)。
        """
        if issubclass(cls, CaseInsensitiveEnum):
            kw.setdefault("enum_class", getattr(self, "enum_class", None))
            kw.setdefault("aliases", getattr(self, "_aliases", None))
        return super().adapt(cls, **kw)

    def _normalize(self, value: Any) -> Any:
        if not isinstance(value, str) or isinstance(value, enum.Enum):
            return value
        upper = value.upper()
        return self._aliases.get(upper, upper)

    def _enum_for(self, value: str) -> Any:
        """把归一化后的字符串解析成枚举成员(大小写与别名都已处理)。"""
        enum_class = getattr(self, "enum_class", None)
        if enum_class is None:
            return value
        try:
            return enum_class[value]
        except KeyError as exc:
            valid = ", ".join(member.name for member in enum_class)
            raise LookupError(
                f"{value!r} 不是 {enum_class.__name__} 的合法取值(可用:{valid})"
            ) from exc

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if isinstance(value, enum.Enum):
            # 以枚举成员名(大写)为唯一落库形式
            return value.name
        if isinstance(value, str):
            return self._enum_for(self._normalize(value)).name
        return None if value is None else str(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        """从库里读出来的一律归一化 + 别名解析。

        不走 `self.impl.process_result_value`,因为 Enum 内部的字符串→成员查表
        在别名/大小写场景下行为不够直观(已在本地复现 'PLATFORM' 抛 LookupError)。
        """
        if value is None:
            return None
        return self._enum_for(self._normalize(value))

    # SQLAlchemy 在 C 扩展构建行处理器时会**直接**调用 impl 层的
    # process / _object_value_for_elem,绕过 TypeDecorator.process_result_value。
    # 因此必须在 bind/result_processor 这两个入口就接管,否则历史值仍会炸。
    def bind_processor(self, dialect: Any) -> Any:
        def process(value: Any) -> Any:
            return self.process_bind_param(value, dialect)

        return process

    def result_processor(self, dialect: Any, coltype: Any = None) -> Any:
        def process(value: Any) -> Any:
            return self.process_result_value(value, dialect)

        return process


def enum_column(
    enum_class: type[E],
    *,
    aliases: Mapping[str, str] | None = None,
    **kwargs: Any,
) -> CaseInsensitiveEnum:
    """声明大小写不敏感的枚举列,用法与 `Enum(...)` 完全一致。"""
    return CaseInsensitiveEnum(enum_class, aliases=aliases, **kwargs)
