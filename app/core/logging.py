"""结构化日志配置(2026-08-09)。

输出 JSON 到 stdout,每条日志带:
  - timestamp / level / logger
  - request_id / trace_id(由 RequestIDMiddleware 注入)
  - user_id / order_id(由 get_log_context 注入)
  - message

部署时由 docker / k8s 收集 stdout(JSON 行),接:
  - 阿里云 SLS(JSON 直读)
  - Loki + Promtail(配 pipeline_stages 解析 JSON)
  - Elasticsearch + Filebeat(同样配 JSON 解析)
"""
from __future__ import annotations

import json
import logging
import logging.config
import os
import socket
import sys
from datetime import datetime, timezone

from .config import settings


_DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
_LOG_FORMAT = os.getenv("LOG_FORMAT", "json").lower()  # json | text
_HOSTNAME = socket.gethostname()


class JsonFormatter(logging.Formatter):
    """输出 JSON 行(每条日志一行),便于被 docker / filebeat / promtail 收集。"""

    def format(self, record: logging.LogRecord) -> str:
        # 基础字段
        log_entry: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # request_id / trace_id 由 middleware 注入到 record.__dict__
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        if hasattr(record, "trace_id"):
            log_entry["trace_id"] = record.trace_id
        if hasattr(record, "user_id"):
            log_entry["user_id"] = record.user_id
        if hasattr(record, "order_id"):
            log_entry["order_id"] = record.order_id
        # 异常
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        # 自定义 extra 字段
        for k, v in record.__dict__.items():
            if k.startswith("_") or k in (
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "message", "module",
                "msecs", "msg", "name", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName", "taskName",
            ):
                continue
            try:
                json.dumps(v)
                log_entry[k] = v
            except (TypeError, ValueError):
                log_entry[k] = repr(v)

        return json.dumps(log_entry, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """开发用的纯文本格式(本地调试时用 LOG_FORMAT=text)。"""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s [%(levelname)s] %(name)s [req=%(request_id)s trc=%(trace_id)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        if not hasattr(record, "trace_id"):
            record.trace_id = "-"
        return super().format(record)


def configure_logging() -> None:
    """应用启动时调用一次。"""
    formatter_class = JsonFormatter if _LOG_FORMAT == "json" else TextFormatter
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {"()": "app.core.logging.JsonFormatter"},
            "text": {"()": "app.core.logging.TextFormatter"},
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "json" if _LOG_FORMAT == "json" else "text",
                "level": _DEFAULT_LOG_LEVEL,
            },
            # 可选 stderr(警告 + 错误进 stderr 方便分流)
            "stderr": {
                "class": "logging.StreamHandler",
                "stream": sys.stderr,
                "formatter": "json" if _LOG_FORMAT == "json" else "text",
                "level": "WARNING",
            },
        },
        "loggers": {
            # 应用日志
            "xiulijiu": {
                "handlers": ["stdout", "stderr"],
                "level": _DEFAULT_LOG_LEVEL,
                "propagate": False,
            },
            "xiulijiu.observability": {
                "handlers": ["stdout", "stderr"],
                "level": _DEFAULT_LOG_LEVEL,
                "propagate": False,
            },
            "xiulijiu.audit": {
                "handlers": ["stdout", "stderr"],
                "level": "INFO",
                "propagate": False,
            },
            "xiulijiu.security": {
                "handlers": ["stdout", "stderr"],
                "level": "INFO",
                "propagate": False,
            },
            # 第三方库降噪
            "uvicorn.access": {
                "handlers": ["stdout"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["stdout", "stderr"],
                "level": _DEFAULT_LOG_LEVEL,
                "propagate": False,
            },
        },
        "root": {
            "handlers": ["stdout", "stderr"],
            "level": _DEFAULT_LOG_LEVEL,
        },
    }
    logging.config.dictConfig(config)


def get_audit_logger() -> logging.Logger:
    """审计日志(资金/订单/提现关键操作,合规要求)。"""
    return logging.getLogger("xiulijiu.audit")


def get_security_logger() -> logging.Logger:
    """安全日志(登录/失败/越权/敏感数据访问)。"""
    return logging.getLogger("xiulijiu.security")
