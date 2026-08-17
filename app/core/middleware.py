"""可观测性中间件 — Request ID + Trace ID + 指标统计(2026-08-09 扩展)。

每个 HTTP 请求自动获得唯一 ID + 累计耗时 + 状态码。
/metrics 端点以 Prometheus 文本格式输出。
"""
from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("xiulijiu.observability")


# 内存指标存储(单进程;多 worker 时各 worker 独立,Prometheus 拉取合并)
class Metrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._requests_total: dict[tuple[str, str], int] = defaultdict(int)  # (method, path) → count
        self._requests_errors: dict[tuple[str, str], int] = defaultdict(int)  # (method, path) → errors (5xx)
        self._requests_status: dict[tuple[str, str, int], int] = defaultdict(int)  # (method, path, status) → count
        self._latency_sum: dict[tuple[str, str], float] = defaultdict(float)  # (method, path) → total seconds
        self._latency_count: dict[tuple[str, str], int] = defaultdict(int)  # (method, path) → count
        self._start_time = time.time()

    def record(self, method: str, path: str, status: int, duration: float) -> None:
        # 规范化 path:把 /api/v1/wallet/balance/123 → /api/v1/wallet/balance/{id}
        # (避免 high cardinality)
        norm = self._normalize(path)
        with self._lock:
            self._requests_total[(method, norm)] += 1
            self._requests_status[(method, norm, status)] += 1
            if status >= 500:
                self._requests_errors[(method, norm)] += 1
            self._latency_sum[(method, norm)] += duration
            self._latency_count[(method, norm)] += 1

    @staticmethod
    def _normalize(path: str) -> str:
        # 把数字 ID 替换成 {id}
        import re
        return re.sub(r"/\d+(?=/|$)", "/{id}", path)

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            # HELP/TYPE 元数据
            lines.append("# HELP xiulijiu_http_requests_total Total HTTP requests")
            lines.append("# TYPE xiulijiu_http_requests_total counter")
            for (m, p), c in sorted(self._requests_total.items()):
                lines.append(f'xiulijiu_http_requests_total{{method="{m}",path="{p}"}} {c}')

            lines.append("# HELP xiulijiu_http_requests_errors_total HTTP 5xx errors")
            lines.append("# TYPE xiulijiu_http_requests_errors_total counter")
            for (m, p), c in sorted(self._requests_errors.items()):
                lines.append(f'xiulijiu_http_requests_errors_total{{method="{m}",path="{p}"}} {c}')

            lines.append("# HELP xiulijiu_http_request_duration_seconds HTTP request latency")
            lines.append("# TYPE xiulijiu_http_request_duration_seconds summary")
            for (m, p), cnt in sorted(self._latency_count.items()):
                total = self._latency_sum[(m, p)]
                avg = total / cnt if cnt else 0
                lines.append(
                    f'xiulijiu_http_request_duration_seconds_sum{{method="{m}",path="{p}"}} {total:.6f}'
                )
                lines.append(
                    f'xiulijiu_http_request_duration_seconds_count{{method="{m}",path="{p}"}} {cnt}'
                )

            lines.append("# HELP xiulijiu_uptime_seconds Process uptime")
            lines.append("# TYPE xiulijiu_uptime_seconds gauge")
            lines.append(f"xiulijiu_uptime_seconds {time.time() - self._start_time:.2f}")
        return "\n".join(lines) + "\n"


# 全局单例
metrics = Metrics()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """为每个请求注入 request_id / trace_id,并统计耗时与状态码。"""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4())[:12])
        request.state.request_id = request_id
        request.state.trace_id = trace_id

        extra = {"request_id": request_id, "trace_id": trace_id}
        start = time.perf_counter()
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as e:
            status = 500
            duration = time.perf_counter() - start
            metrics.record(request.method, request.url.path, status, duration)
            logger.exception(
                f"[{request_id}] {request.method} {request.url.path} -> 500 ({duration:.3f}s)",
                extra=extra,
            )
            raise

        duration = time.perf_counter() - start
        metrics.record(request.method, request.url.path, status, duration)

        level = logging.WARNING if status >= 500 else logging.INFO
        logger.log(
            level,
            f"[{request_id}] {request.method} {request.url.path} -> {status} ({duration:.3f}s)",
            extra=extra,
        )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        return response


def get_log_context(user_id: int | None = None, order_id: int | None = None) -> dict:
    """构建结构化日志上下文"""
    ctx: dict = {}
    if user_id:
        ctx["user_id"] = user_id
    if order_id:
        ctx["order_id"] = order_id
    return ctx
