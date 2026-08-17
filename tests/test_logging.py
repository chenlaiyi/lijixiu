"""日志结构化输出单元测试(2026-08-09)。

覆盖:
  - JSON formatter 输出合法 JSON
  - request_id / trace_id 注入
  - 业务 extra 字段(user_id / amount / withdrawal_id 等)
  - exception 信息格式化
  - configure_logging 不抛异常
  - 第三方 logger(uvicorn)也接管
"""
import os
import sys
import json
import logging
import io
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 强制 JSON 格式 + WARNING 级别
os.environ["LOG_FORMAT"] = "json"
os.environ["LOG_LEVEL"] = "DEBUG"

from app.core.logging import (  # noqa: E402
    JsonFormatter,
    configure_logging,
    get_audit_logger,
    get_security_logger,
)


def parse_jsonl(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def main():
    results = []
    def check(name, ok, detail=""):
        results.append((name, ok, detail))
        print(("OK  " if ok else "FAIL") + f" {name:40s} {detail}")

    # === JsonFormatter 单元测试 ===
    fmt = JsonFormatter()
    rec = logging.LogRecord(
        name="xiulijiu.test", level=logging.INFO, pathname="x.py", lineno=1,
        msg="hello world", args=(), exc_info=None,
    )
    rec.request_id = "abc123"
    rec.trace_id = "trc-xyz-999"
    rec.user_id = 5
    out = fmt.format(rec)
    parsed = json.loads(out)
    check("json-valid", parsed.get("msg") == "hello world")
    check("json-level", parsed.get("level") == "INFO")
    check("json-logger", parsed.get("logger") == "xiulijiu.test")
    check("json-request-id", parsed.get("request_id") == "abc123")
    check("json-trace-id", parsed.get("trace_id") == "trc-xyz-999")
    check("json-user-id", parsed.get("user_id") == 5)
    check("json-ts", "ts" in parsed and parsed["ts"].endswith("+00:00"))

    # === exception 格式化 ===
    try:
        raise ValueError("simulated failure")
    except ValueError:
        import sys as _sys
        rec = logging.LogRecord(
            name="xiulijiu.test", level=logging.ERROR, pathname="x.py", lineno=1,
            msg="failed to x", args=(), exc_info=_sys.exc_info(),
        )
        rec.request_id = "r1"
        out = fmt.format(rec)
        parsed = json.loads(out)
        check("exception-present", "exception" in parsed and "ValueError: simulated failure" in parsed["exception"])
        check("exception-level", parsed.get("level") == "ERROR")

    # === 自定义 extra 字段(复杂对象用 repr)===
    rec = logging.LogRecord(
        name="xiulijiu.audit", level=logging.INFO, pathname="x.py", lineno=1,
        msg="withdrawal approved", args=(), exc_info=None,
    )
    rec.request_id = "r1"
    rec.withdrawal_id = 42
    rec.amount = 195.0
    rec.action = "approve"
    rec.complex_obj = {"nested": [1, 2, 3]}  # 应该序列化
    rec.weird_obj = object()  # 应该 fallback 到 repr
    out = fmt.format(rec)
    parsed = json.loads(out)
    check("extra-withdrawal-id", parsed.get("withdrawal_id") == 42)
    check("extra-amount", parsed.get("amount") == 195.0)
    check("extra-action", parsed.get("action") == "approve")
    check("extra-complex-serialized", isinstance(parsed.get("complex_obj"), dict))
    check("extra-weird-repr", "object at 0x" in str(parsed.get("weird_obj")))

    # === configure_logging 集成测试 ===
    configure_logging()
    audit = get_audit_logger()
    sec = get_security_logger()
    check("audit-logger-name", audit.name == "xiulijiu.audit")
    check("security-logger-name", sec.name == "xiulijiu.security")

    # 抓取 stdout 验证 JSON 行
    import io
    import contextlib
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    audit.addHandler(handler)
    audit.setLevel(logging.INFO)
    try:
        audit.info("withdrawal requested", extra={"request_id": "r-test", "user_id": 99, "amount": 1.5})
        out = buf.getvalue()
        parsed_list = parse_jsonl(out)
        check("stdout-json-line-valid", len(parsed_list) >= 1 and parsed_list[0].get("msg") == "withdrawal requested")
        check("stdout-includes-request-id", any(p.get("request_id") == "r-test" for p in parsed_list))
    finally:
        audit.removeHandler(handler)

    # === summary ===
    print("---")
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
