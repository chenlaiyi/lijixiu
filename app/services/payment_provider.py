"""Payment gateway adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..models.pay_order import PayOrder
from . import wechat_pay


@dataclass
class PayResult:
    success: bool
    transaction_id: str | None = None
    message: str = ""


@dataclass
class PaymentIntent:
    pay_url: str
    payment_params: dict[str, Any] | None = field(default_factory=dict)
    prepay_id: str | None = None
    payer_openid: str | None = None


class BasePaymentProvider(ABC):
    @abstractmethod
    async def create_payment(
        self,
        pay_order: PayOrder,
        *,
        payer_openid: str | None = None,
        js_code: str | None = None,
    ) -> PaymentIntent:
        ...

    @abstractmethod
    async def verify_callback(
        self, pay_order: PayOrder, transaction_id: str | None
    ) -> PayResult:
        ...


class MockPaymentProvider(BasePaymentProvider):
    async def create_payment(
        self,
        pay_order: PayOrder,
        *,
        payer_openid: str | None = None,
        js_code: str | None = None,
    ) -> PaymentIntent:
        return PaymentIntent(pay_url=f"mock://pay/{pay_order.id}")

    async def verify_callback(
        self, pay_order: PayOrder, transaction_id: str | None
    ) -> PayResult:
        return PayResult(
            success=True,
            transaction_id=transaction_id or f"mock_txn_{pay_order.id}",
            message="mock payment success",
        )


class WeChatPayAdapter(BasePaymentProvider):
    async def create_payment(
        self,
        pay_order: PayOrder,
        *,
        payer_openid: str | None = None,
        js_code: str | None = None,
    ) -> PaymentIntent:
        intent = wechat_pay.create_jsapi_payment(
            pay_order,
            payer_openid=payer_openid,
            js_code=js_code,
        )
        return PaymentIntent(
            pay_url=intent.pay_url,
            payment_params=intent.payment_params,
            prepay_id=intent.prepay_id,
            payer_openid=intent.payer_openid,
        )

    async def verify_callback(self, pay_order: PayOrder, tx_id: str | None) -> PayResult:
        return PayResult(
            success=False,
            message="wechat payments must be confirmed by official notify or server query",
        )


class AlipayAdapter(BasePaymentProvider):
    async def create_payment(
        self,
        pay_order: PayOrder,
        *,
        payer_openid: str | None = None,
        js_code: str | None = None,
    ) -> PaymentIntent:
        raise NotImplementedError("alipay is not integrated")

    async def verify_callback(self, pay_order: PayOrder, tx_id: str | None) -> PayResult:
        raise NotImplementedError("alipay is not integrated")


_providers = {
    "mock": MockPaymentProvider(),
    "wechat": WeChatPayAdapter(),
    "alipay": AlipayAdapter(),
}


def get_provider(name: str) -> BasePaymentProvider:
    p = _providers.get(name)
    if p is None:
        raise ValueError(f"unsupported payment provider: {name}")
    return p
