"""WeChat Pay API v3 client."""

from __future__ import annotations

import base64
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.x509.oid import NameOID

from ..core.config import settings
from ..models.pay_order import PayOrder

WECHAT_PAY_HOST = "https://api.mch.weixin.qq.com"


@dataclass
class WeChatPaymentIntent:
    pay_url: str
    payment_params: dict[str, str]
    prepay_id: str
    payer_openid: str


@dataclass
class WeChatRefundResult:
    refund_id: str | None
    status: str
    payload: dict[str, Any]


@dataclass
class WeChatTransferResult:
    out_bill_no: str
    transfer_bill_no: str | None
    state: str
    payload: dict[str, Any]


class WeChatPayError(RuntimeError):
    pass


_private_key: rsa.RSAPrivateKey | None = None
_merchant_cert: x509.Certificate | None = None
_platform_certs: dict[str, x509.Certificate] = {}
_access_token_cache: dict[str, str | float] = {"token": "", "expires_at": 0.0}

# 2026-08-09: 平台证书下载防御(避免 WeChat 偶发 403 / 限频时反复打)
_PLATFORM_CERT_DOWNLOAD_INTERVAL = 600.0  # 失败后最少 10 分钟再重试
_platform_cert_download_state: dict[str, float | str] = {
    "last_attempt_at": 0.0,
    "last_error": "",
    "consecutive_failures": 0,
}


def _read_json(data: bytes) -> dict[str, Any]:
    if not data:
        return {}
    return json.loads(data.decode("utf-8"))


def _json_dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _path(path: str) -> Path:
    value = Path(path)
    if value.is_absolute():
        return value
    return Path.cwd() / value


def _api_v3_key() -> str:
    key = settings.WECHAT_PAY_API_V3_KEY
    if not key:
        raise WeChatPayError("WECHAT_PAY_API_V3_KEY is not configured")
    if len(key.encode("utf-8")) != 32:
        raise WeChatPayError("WECHAT_PAY_API_V3_KEY must be 32 bytes")
    return key


def _load_private_key() -> rsa.RSAPrivateKey:
    global _private_key
    if _private_key is not None:
        return _private_key
    key_path = _path(settings.WECHAT_PAY_KEY_PATH)
    if not key_path.exists():
        raise WeChatPayError(f"merchant private key not found: {key_path}")
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise WeChatPayError("merchant private key must be an RSA private key")
    _private_key = key
    return key


def _load_merchant_cert() -> x509.Certificate:
    global _merchant_cert
    if _merchant_cert is not None:
        return _merchant_cert
    cert_path = _path(settings.WECHAT_PAY_CERT_PATH)
    if not cert_path.exists():
        raise WeChatPayError(f"merchant certificate not found: {cert_path}")
    _merchant_cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    return _merchant_cert


def merchant_serial_no() -> str:
    if settings.WECHAT_PAY_CERT_SERIAL_NO:
        return settings.WECHAT_PAY_CERT_SERIAL_NO.strip().upper()
    return format(_load_merchant_cert().serial_number, "X").upper()


def mch_id() -> str:
    if settings.WECHAT_PAY_MCH_ID:
        return settings.WECHAT_PAY_MCH_ID.strip()
    attrs = _load_merchant_cert().subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if attrs and attrs[0].value:
        return attrs[0].value
    raise WeChatPayError("WECHAT_PAY_MCH_ID is not configured")


def notify_url() -> str:
    if settings.WECHAT_PAY_NOTIFY_URL:
        return settings.WECHAT_PAY_NOTIFY_URL
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/api/v1/payment/wechat/notify"


def refund_notify_url() -> str:
    if settings.WECHAT_REFUND_NOTIFY_URL:
        return settings.WECHAT_REFUND_NOTIFY_URL
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/api/v1/payment/wechat/refund-notify"


def transfer_notify_url() -> str:
    if settings.WECHAT_TRANSFER_NOTIFY_URL:
        return settings.WECHAT_TRANSFER_NOTIFY_URL
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/api/v1/wallet/wechat/transfer-notify"


def config_status() -> dict[str, Any]:
    cert_path = _path(settings.WECHAT_PAY_CERT_PATH)
    key_path = _path(settings.WECHAT_PAY_KEY_PATH)
    issues: list[str] = []

    api_v3_key_ready = len((settings.WECHAT_PAY_API_V3_KEY or "").encode("utf-8")) == 32
    if not api_v3_key_ready:
        issues.append("WECHAT_PAY_API_V3_KEY missing or not 32 bytes")
    if not settings.WECHAT_APP_SECRET:
        issues.append("WECHAT_APP_SECRET missing; cannot exchange wx.login code for openid")
    if not cert_path.exists():
        issues.append(f"merchant certificate not found: {cert_path}")
    if not key_path.exists():
        issues.append(f"merchant private key not found: {key_path}")

    merchant_id = ""
    serial_no = ""
    if cert_path.exists():
        try:
            merchant_id = mch_id()
            serial_no = merchant_serial_no()
        except Exception as exc:
            issues.append(f"merchant certificate read failed: {exc}")

    transfer_issues = transfer_config_issues()
    return {
        "ready": not issues,
        "mock_payment_enabled": bool(settings.PAYMENT_ALLOW_MOCK),
        "appid": settings.WECHAT_PAY_APPID,
        "mch_id": merchant_id or settings.WECHAT_PAY_MCH_ID,
        "merchant_serial_no": serial_no or settings.WECHAT_PAY_CERT_SERIAL_NO,
        "notify_url": notify_url(),
        "refund_notify_url": refund_notify_url(),
        "cert_path": str(cert_path),
        "key_path": str(key_path),
        "cert_exists": cert_path.exists(),
        "key_exists": key_path.exists(),
        "api_v3_key_configured": api_v3_key_ready,
        "app_secret_configured": bool(settings.WECHAT_APP_SECRET),
        "transfer_auto_enabled": bool(settings.WECHAT_WITHDRAW_AUTO_TRANSFER),
        "transfer_scene_id_configured": bool(settings.WECHAT_TRANSFER_SCENE_ID),
        "transfer_ready": not transfer_issues,
        "transfer_issues": transfer_issues,
        "issues": issues,
    }


def transfer_config_issues() -> list[str]:
    issues: list[str] = []
    if not settings.WECHAT_TRANSFER_SCENE_ID:
        issues.append("WECHAT_TRANSFER_SCENE_ID missing")
    if not settings.WECHAT_APP_SECRET:
        issues.append("WECHAT_APP_SECRET missing; withdrawal users may lack openid")
    return issues


def _sign(message: str) -> str:
    signature = _load_private_key().sign(
        message.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def _authorization(method: str, canonical_url: str, body: str) -> str:
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    message = f"{method}\n{canonical_url}\n{timestamp}\n{nonce}\n{body}\n"
    signature = _sign(message)
    return (
        "WECHATPAY2-SHA256-RSA2048 "
        f'mchid="{mch_id()}",'
        f'nonce_str="{nonce}",'
        f'signature="{signature}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{merchant_serial_no()}"'
    )


def _wechat_request(method: str, canonical_url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = _json_dumps(payload or {}) if payload is not None else ""
    data = body.encode("utf-8") if body else None
    req = Request(
        f"{WECHAT_PAY_HOST}{canonical_url}",
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": _authorization(method, canonical_url, body),
            "User-Agent": "xiulijiu-wechat-pay/1.0",
        },
    )
    try:
        with urlopen(req, timeout=20) as resp:
            return _read_json(resp.read())
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise WeChatPayError(f"WeChat Pay request failed ({exc.code}): {detail}") from exc


def _decrypt_resource_bytes(resource: dict[str, Any]) -> bytes:
    ciphertext = base64.b64decode(resource["ciphertext"])
    nonce = resource["nonce"].encode("utf-8")
    associated_data = (resource.get("associated_data") or "").encode("utf-8")
    return AESGCM(_api_v3_key().encode("utf-8")).decrypt(
        nonce,
        ciphertext,
        associated_data,
    )


def _decrypt_resource(resource: dict[str, Any]) -> dict[str, Any]:
    return json.loads(_decrypt_resource_bytes(resource).decode("utf-8"))


def _load_platform_cert_from_file(serial_no: str) -> x509.Certificate | None:
    if not settings.WECHAT_PAY_PLATFORM_CERT_PATH:
        return None
    path = _path(settings.WECHAT_PAY_PLATFORM_CERT_PATH)
    if not path.exists():
        return None
    cert = x509.load_pem_x509_certificate(path.read_bytes())
    if format(cert.serial_number, "X").upper() == serial_no.upper():
        return cert
    return None


def _download_platform_certs() -> None:
    """下载并解密 WeChat 平台证书。

    2026-08-09 加防御:
      - 失败后 10 分钟内不重试(避免 WeChat 偶发 403 / 限频时被反复打)
      - 失败计数,>=3 次时 security logger 告警(让 watcher 推到钉钉/飞书)
    """
    import logging
    from time import time as _now

    last_attempt = float(_platform_cert_download_state.get("last_attempt_at") or 0.0)
    elapsed = _now() - last_attempt
    if last_attempt > 0 and elapsed < _PLATFORM_CERT_DOWNLOAD_INTERVAL:
        cached_err = str(_platform_cert_download_state.get("last_error") or "")
        if cached_err:
            raise WeChatPayError(
                f"WeChat platform cert download in cooldown "
                f"({int(elapsed)}s < {int(_PLATFORM_CERT_DOWNLOAD_INTERVAL)}s): {cached_err}"
            )

    _platform_cert_download_state["last_attempt_at"] = _now()
    try:
        data = _wechat_request("GET", "/v3/certificates")
    except WeChatPayError as exc:
        _platform_cert_download_state["consecutive_failures"] = (
            int(_platform_cert_download_state.get("consecutive_failures") or 0) + 1
        )
        _platform_cert_download_state["last_error"] = str(exc)
        if int(_platform_cert_download_state["consecutive_failures"]) >= 3:
            logging.getLogger("xiulijiu.security").warning(
                "WeChat platform cert download failed %d times: %s — "
                "this means payment notifications WILL fail signature verification. "
                "Action: call 95017 OR set WECHAT_PAY_PLATFORM_CERT_PATH to a local cert.",
                _platform_cert_download_state["consecutive_failures"],
                exc,
            )
        raise
    else:
        _platform_cert_download_state["consecutive_failures"] = 0
        _platform_cert_download_state["last_error"] = ""

    for item in data.get("data", []):
        serial_no = str(item.get("serial_no") or "").upper()
        resource = item.get("encrypt_certificate") or {}
        if not serial_no or not resource:
            continue
        certificate = _decrypt_resource_bytes(resource)
        if certificate:
            _platform_certs[serial_no] = x509.load_pem_x509_certificate(certificate)


def platform_cert_status() -> dict[str, Any]:
    """诊断用:返回平台证书下载的当前状态,给 /admin/diagnostics 用。"""
    from time import time as _now
    last_attempt = float(_platform_cert_download_state.get("last_attempt_at") or 0.0)
    return {
        "cached_count": len(_platform_certs),
        "cached_serials": sorted(_platform_certs.keys()),
        "last_attempt_at": last_attempt,
        "seconds_since_last_attempt": int(_now() - last_attempt) if last_attempt else None,
        "consecutive_failures": int(_platform_cert_download_state.get("consecutive_failures") or 0),
        "last_error": str(_platform_cert_download_state.get("last_error") or ""),
        "cooldown_active": (
            last_attempt > 0
            and (_now() - last_attempt) < _PLATFORM_CERT_DOWNLOAD_INTERVAL
        ),
        "cooldown_seconds": int(_PLATFORM_CERT_DOWNLOAD_INTERVAL),
    }


def _platform_cert(serial_no: str) -> x509.Certificate:
    serial_no = serial_no.upper()
    if serial_no in _platform_certs:
        return _platform_certs[serial_no]
    file_cert = _load_platform_cert_from_file(serial_no)
    if file_cert is not None:
        _platform_certs[serial_no] = file_cert
        return file_cert
    _download_platform_certs()
    cert = _platform_certs.get(serial_no)
    if cert is None:
        raise WeChatPayError(f"WeChat Pay platform certificate not found: {serial_no}")
    return cert


def verify_notification_signature(headers: dict[str, str], body: str) -> None:
    serial_no = headers.get("wechatpay-serial") or headers.get("Wechatpay-Serial") or ""
    timestamp = headers.get("wechatpay-timestamp") or headers.get("Wechatpay-Timestamp") or ""
    nonce = headers.get("wechatpay-nonce") or headers.get("Wechatpay-Nonce") or ""
    signature = headers.get("wechatpay-signature") or headers.get("Wechatpay-Signature") or ""
    if not all([serial_no, timestamp, nonce, signature]):
        raise WeChatPayError("WeChat Pay notification signature headers are incomplete")

    message = f"{timestamp}\n{nonce}\n{body}\n".encode("utf-8")
    try:
        _platform_cert(serial_no).public_key().verify(
            base64.b64decode(signature),
            message,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except InvalidSignature as exc:
        raise WeChatPayError("WeChat Pay notification signature verification failed") from exc


def parse_notification(headers: dict[str, str], body: str) -> dict[str, Any]:
    verify_notification_signature(headers, body)
    payload = json.loads(body)
    return _decrypt_resource(payload["resource"])


def _prepay_payload(pay_order: PayOrder, payer_openid: str) -> dict[str, Any]:
    cents = int(round(float(pay_order.amount) * 100))
    if cents <= 0:
        raise WeChatPayError("payment amount must be greater than 0")
    return {
        "appid": settings.WECHAT_PAY_APPID,
        "mchid": mch_id(),
        "description": f"xiulijiu order #{pay_order.order_id}"[:127],
        "out_trade_no": pay_order.out_trade_no,
        "notify_url": notify_url(),
        "amount": {"total": cents, "currency": "CNY"},
        "payer": {"openid": payer_openid},
    }


def build_jsapi_payment_params(prepay_id: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    package_value = f"prepay_id={prepay_id}"
    message = f"{settings.WECHAT_PAY_APPID}\n{timestamp}\n{nonce}\n{package_value}\n"
    return {
        "timeStamp": timestamp,
        "nonceStr": nonce,
        "package": package_value,
        "signType": "RSA",
        "paySign": _sign(message),
    }


def exchange_js_code(js_code: str) -> str:
    if not settings.WECHAT_APP_SECRET:
        raise WeChatPayError("WECHAT_APP_SECRET is not configured")
    query = urlencode({
        "appid": settings.WECHAT_PAY_APPID,
        "secret": settings.WECHAT_APP_SECRET,
        "js_code": js_code,
        "grant_type": "authorization_code",
    })
    req = Request(f"https://api.weixin.qq.com/sns/jscode2session?{query}", method="GET")
    with urlopen(req, timeout=15) as resp:
        data = _read_json(resp.read())
    if data.get("errcode"):
        raise WeChatPayError(f"wx.login code exchange failed: {data.get('errmsg')}")
    openid = data.get("openid")
    if not openid:
        raise WeChatPayError("wx.login code exchange did not return openid")
    return str(openid)


def _get_access_token() -> str:
    if not settings.WECHAT_APP_SECRET:
        raise WeChatPayError("WECHAT_APP_SECRET is not configured")

    now = time.time()
    cached_token = str(_access_token_cache.get("token") or "")
    expires_at = float(_access_token_cache.get("expires_at") or 0)
    if cached_token and expires_at > now + 60:
        return cached_token

    query = urlencode({
        "grant_type": "client_credential",
        "appid": settings.WECHAT_PAY_APPID,
        "secret": settings.WECHAT_APP_SECRET,
    })
    req = Request(f"https://api.weixin.qq.com/cgi-bin/token?{query}", method="GET")
    with urlopen(req, timeout=15) as resp:
        data = _read_json(resp.read())
    if data.get("errcode"):
        raise WeChatPayError(f"WeChat access token failed: {data.get('errmsg')}")

    token = str(data.get("access_token") or "")
    if not token:
        raise WeChatPayError(f"WeChat access token missing: {data}")

    expires_in = int(data.get("expires_in") or 7200)
    _access_token_cache["token"] = token
    _access_token_cache["expires_at"] = now + max(expires_in - 300, 60)
    return token


def exchange_phone_code(phone_code: str) -> str:
    access_token = _get_access_token()
    body = _json_dumps({"code": phone_code}).encode("utf-8")
    query = urlencode({"access_token": access_token})
    req = Request(
        f"https://api.weixin.qq.com/wxa/business/getuserphonenumber?{query}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=15) as resp:
        data = _read_json(resp.read())
    if data.get("errcode"):
        raise WeChatPayError(f"WeChat phone code exchange failed: {data.get('errmsg')}")

    phone_info = data.get("phone_info") or {}
    phone = phone_info.get("purePhoneNumber") or phone_info.get("phoneNumber")
    if not phone:
        raise WeChatPayError(f"WeChat phone number missing: {data}")
    return str(phone)


def get_mini_program_code(scene: str, page: str) -> bytes:
    """Generate a WeChat mini-program code without exposing order details."""
    access_token = _get_access_token()
    query = urlencode({"access_token": access_token})
    body = _json_dumps({
        "scene": scene,
        "page": page,
        "check_path": False,
        "env_version": settings.WECHAT_MINIPROGRAM_ENV_VERSION,
        "width": 430,
    }).encode("utf-8")
    req = Request(
        f"https://api.weixin.qq.com/wxa/getwxacodeunlimit?{query}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=20) as resp:
        content = resp.read()
        content_type = resp.headers.get("Content-Type", "")
    if "json" in content_type or content.startswith(b"{"):
        data = _read_json(content)
        raise WeChatPayError(f"Mini-program code generation failed: {data.get('errmsg') or data}")
    return content


def create_jsapi_payment(
    pay_order: PayOrder,
    payer_openid: str | None = None,
    js_code: str | None = None,
) -> WeChatPaymentIntent:
    openid = payer_openid or (exchange_js_code(js_code) if js_code else "")
    if not openid:
        raise WeChatPayError("payer_openid or js_code is required for JSAPI payment")
    data = _wechat_request("POST", "/v3/pay/transactions/jsapi", _prepay_payload(pay_order, openid))
    prepay_id = data.get("prepay_id")
    if not prepay_id:
        raise WeChatPayError(f"WeChat Pay did not return prepay_id: {data}")
    return WeChatPaymentIntent(
        pay_url=f"wechat://pay/{pay_order.id}",
        payment_params=build_jsapi_payment_params(str(prepay_id)),
        prepay_id=str(prepay_id),
        payer_openid=openid,
    )


def query_transaction(out_trade_no: str) -> dict[str, Any]:
    encoded = quote(out_trade_no, safe="")
    query = urlencode({"mchid": mch_id()})
    return _wechat_request("GET", f"/v3/pay/transactions/out-trade-no/{encoded}?{query}")


def create_refund(
    pay_order: PayOrder,
    out_refund_no: str,
    refund_amount: float,
    reason: str | None = None,
) -> WeChatRefundResult:
    refund_cents = int(round(float(refund_amount) * 100))
    total_cents = int(round(float(pay_order.amount) * 100))
    if refund_cents <= 0:
        raise WeChatPayError("refund amount must be greater than 0")
    payload: dict[str, Any] = {
        "out_trade_no": pay_order.out_trade_no,
        "out_refund_no": out_refund_no,
        "reason": (reason or "refund")[:80],
        "notify_url": refund_notify_url(),
        "amount": {
            "refund": refund_cents,
            "total": total_cents,
            "currency": "CNY",
        },
    }
    data = _wechat_request("POST", "/v3/refund/domestic/refunds", payload)
    return WeChatRefundResult(
        refund_id=data.get("refund_id"),
        status=str(data.get("status") or "PROCESSING").lower(),
        payload=data,
    )


def query_refund(out_refund_no: str) -> dict[str, Any]:
    encoded = quote(out_refund_no, safe="")
    return _wechat_request("GET", f"/v3/refund/domestic/refunds/{encoded}")


def create_transfer_bill(
    out_bill_no: str,
    openid: str,
    amount: float,
    remark: str | None = None,
) -> WeChatTransferResult:
    if not settings.WECHAT_TRANSFER_SCENE_ID:
        raise WeChatPayError("WECHAT_TRANSFER_SCENE_ID is not configured")
    cents = int(round(float(amount) * 100))
    if cents <= 0:
        raise WeChatPayError("transfer amount must be greater than 0")
    payload = {
        "appid": settings.WECHAT_PAY_APPID,
        "out_bill_no": out_bill_no,
        "transfer_scene_id": settings.WECHAT_TRANSFER_SCENE_ID,
        "openid": openid,
        "transfer_amount": cents,
        "transfer_remark": (remark or settings.WECHAT_TRANSFER_REMARK or "withdrawal")[:32],
        "notify_url": transfer_notify_url(),
        "user_recv_perception": settings.WECHAT_TRANSFER_USER_RECV_PERCEPTION or "withdrawal",
    }
    data = _wechat_request("POST", "/v3/fund-app/mch-transfer/transfer-bills", payload)
    state = str(data.get("state") or data.get("status") or "PROCESSING").lower()
    return WeChatTransferResult(
        out_bill_no=str(data.get("out_bill_no") or out_bill_no),
        transfer_bill_no=data.get("transfer_bill_no"),
        state=state,
        payload=data,
    )


def query_transfer_bill(out_bill_no: str) -> dict[str, Any]:
    encoded = quote(out_bill_no, safe="")
    query = urlencode({"mchid": mch_id()})
    return _wechat_request(
        "GET",
        f"/v3/fund-app/mch-transfer/transfer-bills/out-bill-no/{encoded}?{query}",
    )
