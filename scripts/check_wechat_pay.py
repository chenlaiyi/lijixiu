"""Check WeChat Pay runtime readiness + end-to-end connectivity.

Usage:
    python scripts/check_wechat_pay.py                    # config only
    python scripts/check_wechat_pay.py --network          # + actually call WeChat API
    python scripts/check_wechat_pay.py --json             # machine-readable output
    python scripts/check_wechat_pay.py --require-transfer # also require transfer (withdraw) ready

Exit codes:
    0 = ready (or --allow-not-ready)
    1 = not ready
    2 = config OK but network call failed
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services import wechat_pay
from app.services.wechat_pay import WeChatPayError


def _check_config() -> dict:
    """Read config status (no network)."""
    return wechat_pay.config_status()


def _check_network() -> dict:
    """Actually call WeChat Pay API to verify credentials + network.

    Steps:
      1. GET /v3/certificates — verifies MCH_ID + merchant cert + private key + signing
      2. Decode the first platform certificate to prove decryption works
    """
    result = {
        "ok": False,
        "step": None,
        "error": None,
        "details": {},
    }
    try:
        # Step 1: fetch platform certs (validates signing + merchant creds + network)
        result["step"] = "GET /v3/certificates"
        t0 = time.time()
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError, URLError

        method = "GET"
        canonical_url = "/v3/certificates"
        body = ""

        # Build authorization header using the same helpers
        from app.services import wechat_pay as wp
        auth = wp._authorization(method, canonical_url, body)
        mch = wp.mch_id()
        serial = wp.merchant_serial_no()

        req = Request(
            f"https://api.mch.weixin.qq.com{canonical_url}",
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": auth,
                "User-Agent": "xiulijiu-wechat-pay-check/1.0",
            },
        )
        try:
            with urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            result["error"] = f"HTTP {exc.code}: {detail[:500]}"
            return result
        except URLError as exc:
            result["error"] = f"network unreachable: {exc.reason}"
            return result

        elapsed_ms = int((time.time() - t0) * 1000)
        certs = data.get("data") or []
        if not certs:
            result["error"] = "WeChat returned 0 platform certificates"
            return result

        # Step 2: try to decrypt the first cert to prove API v3 key works
        result["step"] = "decrypt platform certificate"
        first = certs[0]
        enc = first.get("encrypt_certificate") or {}
        try:
            plain = wp._decrypt_resource_bytes(enc)
        except WeChatPayError as exc:
            result["error"] = f"API_V3_KEY decrypt failed: {exc}"
            return result
        except Exception as exc:
            result["error"] = f"unexpected decrypt error: {exc}"
            return result

        from cryptography import x509
        cert = x509.load_pem_x509_certificate(plain)
        cert_serial = format(cert.serial_number, "X").upper()
        result["details"] = {
            "mch_id": mch,
            "merchant_serial_no": serial,
            "platform_certs_count": len(certs),
            "first_cert_serial": cert_serial,
            "first_cert_subject": cert.subject.rfc4514_string(),
            "first_cert_expires": cert.not_valid_after_utc.isoformat(),
            "elapsed_ms": elapsed_ms,
        }
        result["ok"] = True
        return result
    except WeChatPayError as exc:
        result["error"] = f"WeChatPayError: {exc}"
        return result
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


def _print_human(config: dict, network: dict | None) -> None:
    print("=" * 60)
    print("WeChat Pay Configuration")
    print("=" * 60)
    print(f"  payment_ready : {config['ready']}")
    print(f"  appid         : {config.get('appid') or '-'}")
    print(f"  mch_id        : {config.get('mch_id') or '-'}")
    print(f"  serial_no     : {config.get('merchant_serial_no') or '-'}")
    print(f"  notify_url    : {config.get('notify_url') or '-'}")
    print(f"  api_v3_key    : {'OK (32 bytes)' if config.get('api_v3_key_configured') else 'MISSING'}")
    print(f"  app_secret    : {'OK' if config.get('app_secret_configured') else 'MISSING'}")
    print(f"  cert          : {config.get('cert_path')} (exists={config.get('cert_exists')})")
    print(f"  key           : {config.get('key_path')} (exists={config.get('key_exists')})")
    print(f"  transfer_ready: {config.get('transfer_ready')}")
    if config.get("issues"):
        print()
        print("  Config issues:")
        for issue in config["issues"]:
            print(f"  - {issue}")
    if config.get("transfer_issues"):
        print()
        print("  Transfer issues:")
        for issue in config["transfer_issues"]:
            print(f"  - {issue}")

    if network is not None:
        print()
        print("=" * 60)
        print("WeChat Pay Network Connectivity")
        print("=" * 60)
        if network.get("ok"):
            d = network["details"]
            print(f"  GET /v3/certificates  : OK ({d.get('elapsed_ms')}ms)")
            print(f"  platform_certs_count  : {d.get('platform_certs_count')}")
            print(f"  first_cert_serial     : {d.get('first_cert_serial')}")
            print(f"  first_cert_subject    : {d.get('first_cert_subject')}")
            print(f"  first_cert_expires    : {d.get('first_cert_expires')}")
        else:
            print(f"  step   : {network.get('step')}")
            print(f"  error  : {network.get('error')}")
            # Surface specific remediation hints
            err = (network.get("error") or "")
            if "平台证书已过期失效" in err or "平台证书" in err:
                print()
                print("  HINT: 微信返回 '平台证书已过期失效' 通常意味着:")
                print("    1. 你的商户号是新的(刚开通 7 月),微信还在初始化平台证书")
                print("    2. 微信的 platform cert 缓存问题 — 等几小时再试")
                print("    3. 真的需要联系微信支付技术支持(电话 95017)")
                print()
                print("  临时绕开:让运营同学从商户平台手动下载 platform cert,")
                print("    放到 cert/wechatpay_cert.pem,然后设环境变量:")
                print("      WECHAT_PAY_PLATFORM_CERT_PATH=cert/wechatpay_cert.pem")
                print("    之后代码会优先用本地 cert,绕开下载.")

    print()
    print("=" * 60)
    overall_ok = config["ready"] and (network is None or network.get("ok"))
    print(f"OVERALL: {'READY ✅' if overall_ok else 'NOT READY ❌'}")
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="machine-readable JSON output")
    parser.add_argument("--network", action="store_true", help="also call WeChat API to verify credentials")
    parser.add_argument("--allow-not-ready", action="store_true", help="always exit 0; useful for non-prod local checks")
    parser.add_argument(
        "--require-transfer",
        action="store_true",
        help="also require WeChat merchant transfer (withdraw) to be ready",
    )
    args = parser.parse_args()

    config = _check_config()
    network = _check_network() if args.network else None

    if args.json:
        out = {"config": config}
        if network is not None:
            out["network"] = network
        out["ready"] = bool(config["ready"]) and (network is None or bool(network.get("ok")))
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        _print_human(config, network)

    ready = bool(config["ready"])
    if args.require_transfer:
        ready = ready and bool(config.get("transfer_ready"))
    if network is not None:
        ready = ready and bool(network.get("ok"))
    return 0 if ready or args.allow_not_ready else (2 if config["ready"] else 1)


if __name__ == "__main__":
    sys.exit(main())
