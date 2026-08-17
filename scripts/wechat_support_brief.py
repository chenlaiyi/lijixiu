"""Generate a customer support brief for calling WeChat Pay (95017).

This is a one-shot helper that produces a copy-paste-ready report the
operator can read out / paste into a WeChat support ticket. It reads the
local merchant certificate and current configuration and assembles:

  - merchant id (derived from cert)
  - merchant cert serial (derived from cert)
  - appid
  - the exact error code + message
  - the API endpoint + timestamp of the failure
  - the local mch_id/cert/key file paths (so support can verify the right
    merchant is being diagnosed)

Usage:
  python scripts/wechat_support_brief.py
  python scripts/wechat_support_brief.py --save docs/wechat-95017-brief.md
  python scripts/wechat_support_brief.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography import x509
from cryptography.x509.oid import NameOID

from app.core.config import settings
from app.services import wechat_pay as wp
from app.services.wechat_pay import WeChatPayError


def _safe_mch_id() -> str:
    try:
        return wp.mch_id()
    except Exception as exc:
        return f"<unavailable: {exc}>"


def _safe_serial() -> str:
    try:
        return wp.merchant_serial_no()
    except Exception as exc:
        return f"<unavailable: {exc}>"


def _cert_subject() -> str:
    try:
        cert_path = Path(settings.WECHAT_PAY_CERT_PATH)
        if not cert_path.is_absolute():
            cert_path = Path.cwd() / cert_path
        if not cert_path.exists():
            return "<cert file not found>"
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        return cert.subject.rfc4514_string()
    except Exception as exc:
        return f"<unavailable: {exc}>"


def _cert_validity() -> tuple[str, str]:
    try:
        cert_path = Path(settings.WECHAT_PAY_CERT_PATH)
        if not cert_path.is_absolute():
            cert_path = Path.cwd() / cert_path
        if not cert_path.exists():
            return ("<cert file not found>", "<cert file not found>")
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        return (
            cert.not_valid_before_utc.isoformat(),
            cert.not_valid_after_utc.isoformat(),
        )
    except Exception:
        return ("<unavailable>", "<unavailable>")


def _probe_live_error() -> dict:
    """Reproduce the network failure once to capture the exact WeChat response."""
    import urllib.request
    import urllib.error
    import secrets
    import base64
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    method = "GET"
    canonical = "/v3/certificates"
    body = ""
    ts = str(int(time.time()))
    nonce = secrets.token_hex(16)
    msg = f"{method}\n{canonical}\n{ts}\n{nonce}\n{body}\n"
    key_path = Path(settings.WECHAT_PAY_KEY_PATH)
    if not key_path.is_absolute():
        key_path = Path.cwd() / key_path
    if not key_path.exists():
        return {"ok": False, "stage": "key file", "error": f"key not found: {key_path}"}
    try:
        priv = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        sig = base64.b64encode(
            priv.sign(msg.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        ).decode()
    except Exception as exc:
        return {"ok": False, "stage": "sign", "error": f"sign failed: {exc}"}
    auth = (
        f'WECHATPAY2-SHA256-RSA2048 mchid="{_safe_mch_id()}",'
        f'nonce_str="{nonce}",signature="{sig}",'
        f'timestamp="{ts}",serial_no="{_safe_serial()}"'
    )
    req = urllib.request.Request(
        "https://api.mch.weixin.qq.com/v3/certificates",
        method="GET",
        headers={"Authorization": auth, "Accept": "application/json", "User-Agent": "xiulijiu-brief/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return {
                "ok": True,
                "stage": "GET /v3/certificates",
                "status": r.status,
                "ts": ts,
            }
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        return {
            "ok": False,
            "stage": "GET /v3/certificates",
            "status": exc.code,
            "ts": ts,
            "error_body": detail[:600],
        }
    except Exception as exc:
        return {"ok": False, "stage": "GET /v3/certificates", "error": f"{type(exc).__name__}: {exc}"}


def _phone_script() -> str:
    """Verbatim 1-paragraph read-out for 95017."""
    return (
        "您好，我是微信支付商户 1481119632 的开发。我们调 "
        "GET /v3/certificates 接口拿平台证书来验签支付回调，"
        "微信返回 HTTP 403，错误码 NOT_ENOUGH，提示 "
        "「平台证书已过期失效，请联系微信支付技术支持」。"
        "我们的 MCH_ID 1481119632、证书序列号 4591395BB783609366C47474379A9B2B5611FEF0，"
        "AppID wx2273201e59e280bc。麻烦后台同事帮我们刷新一下平台证书，"
        "或者告诉我们是不是新商户号还在初始化期，需要等多久。"
        "工单参考我会在系统里挂一个 trace_id，等你们回复。"
    )


def _build_report() -> dict:
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    cert_nb, cert_na = _cert_validity()
    probe = _probe_live_error()
    report = {
        "generated_at": now,
        "merchant": {
            "mch_id": _safe_mch_id(),
            "appid": settings.WECHAT_PAY_APPID,
            "merchant_cert_serial": _safe_serial(),
            "merchant_cert_subject": _cert_subject(),
            "merchant_cert_validity": {"not_before": cert_nb, "not_after": cert_na},
            "cert_path": str(Path(settings.WECHAT_PAY_CERT_PATH).resolve()),
            "key_path": str(Path(settings.WECHAT_PAY_KEY_PATH).resolve()),
            "platform_cert_local_path": settings.WECHAT_PAY_PLATFORM_CERT_PATH or "<not set>",
        },
        "problem": {
            "endpoint": "GET https://api.mch.weixin.qq.com/v3/certificates",
            "purpose": "Download WeChat platform certificates (used to verify payment/refund/transfer notification signatures)",
            "observed": probe,
        },
        "env": {
            "public_base_url": settings.PUBLIC_BASE_URL,
            "pay_notify_url": wp.notify_url(),
            "refund_notify_url": wp.refund_notify_url(),
            "transfer_notify_url": wp.transfer_notify_url(),
            "miniprogram_env_version": settings.WECHAT_MINIPROGRAM_ENV_VERSION,
            "mock_payment_enabled": settings.PAYMENT_ALLOW_MOCK,
        },
        "phone_script_zh": _phone_script(),
        "trace_id_hint": (
            "在系统里 POST /api/v1/admin/reconcile/run 之后,"
            "用 journalctl -u xiulijiu-api | grep '\"request_id\"' 拿一个 trace_id,"
            "工单里附上,微信能直接定位到你的请求时间窗。"
        ),
    }
    return report


def _to_markdown(report: dict) -> str:
    m = report["merchant"]
    p = report["problem"]
    obs = p["observed"]
    e = report["env"]
    md = []
    md.append("# 微信支付技术支持工单 — 故障简报")
    md.append("")
    md.append(f"生成时间:{report['generated_at']}")
    md.append("")
    md.append("## 商户信息")
    md.append("")
    md.append(f"- MCH_ID:`{m['mch_id']}`")
    md.append(f"- AppID:`{m['appid']}`")
    md.append(f"- 商户证书序列号:`{m['merchant_cert_serial']}`")
    md.append(f"- 商户证书主体:`{m['merchant_cert_subject']}`")
    md.append(f"- 商户证书有效期:`{m['merchant_cert_validity']['not_before']}` → `{m['merchant_cert_validity']['not_after']}`")
    md.append(f"- 商户证书路径:`{m['cert_path']}`")
    md.append(f"- 私钥路径:`{m['key_path']}`")
    md.append(f"- 平台证书本地路径(若已下载):`{m['platform_cert_local_path']}`")
    md.append("")
    md.append("## 故障现象")
    md.append("")
    md.append(f"- 接口:`{p['endpoint']}`")
    md.append(f"- 用途:{p['purpose']}")
    if obs.get("ok"):
        md.append(f"- 实测:**HTTP {obs.get('status')} OK** — 平台证书下载正常,可能已恢复,请重试。")
    else:
        md.append(f"- 实测阶段:`{obs.get('stage')}`")
        md.append(f"- HTTP 状态:`{obs.get('status', '-')}`")
        md.append(f"- 错误响应:`{obs.get('error_body', obs.get('error', '-'))}`")
        md.append(f"- 本地时间戳:`{obs.get('ts', '-')}`")
    md.append("")
    md.append("## 环境信息")
    md.append("")
    md.append(f"- 回调地址 pay:`{e['pay_notify_url']}`")
    md.append(f"- 回调地址 refund:`{e['refund_notify_url']}`")
    md.append(f"- 回调地址 transfer:`{e['transfer_notify_url']}`")
    md.append(f"- PUBLIC_BASE_URL:`{e['public_base_url']}`")
    md.append(f"- 小程序环境版本:`{e['miniprogram_env_version']}`")
    md.append("")
    md.append("## 电话要点(直接念)")
    md.append("")
    md.append("> " + report["phone_script_zh"])
    md.append("")
    md.append("## 工单 trace_id 怎么拿")
    md.append("")
    md.append("> " + report["trace_id_hint"])
    md.append("")
    md.append("## 临时绕开方案(如果电话等不及)")
    md.append("")
    md.append("1. 让运营从商户平台 → API 安全 → 平台证书管理,下载 `wechatpay_cert.pem`")
    md.append("2. 放到服务器 `/opt/xiulijiu/cert/wechatpay_cert.pem`")
    md.append("3. 在 `.env` 加 `WECHAT_PAY_PLATFORM_CERT_PATH=cert/wechatpay_cert.pem`")
    md.append("4. 重启 api,代码会优先用本地 cert 验签,绕开 `/v3/certificates` 拉取")
    md.append("")
    return "\n".join(md)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="machine-readable JSON")
    parser.add_argument("--save", help="save to file (markdown if .md, json otherwise)")
    parser.add_argument("--no-probe", action="store_true", help="skip live network probe (faster)")
    args = parser.parse_args()

    if args.no_probe:
        # Patch the live probe to a stub
        global _probe_live_error
        _probe_live_error = lambda: {"ok": None, "skipped": True}  # noqa: E731
    report = _build_report()
    if args.json or (args.save and not str(args.save).endswith(".md")):
        out = json.dumps(report, ensure_ascii=False, indent=2)
    else:
        out = _to_markdown(report)

    if args.save:
        Path(args.save).write_text(out, encoding="utf-8")
        print(f"saved: {args.save} ({len(out)} bytes)")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
