"""Where the shop sends the customer to pay: the provider's checkout page when it is
configured, otherwise straight to the shop's payment result page (development: the
payment is then completed by a simulator)."""

import base64
from decimal import Decimal
from urllib.parse import urlencode
from uuid import UUID

from app.core.config import Settings
from contracts.enums import PaymentProvider
from contracts.money import TIYIN_IN_SOM


def result_url(settings: Settings, order_id: UUID, provider: PaymentProvider) -> str:
    return f"{settings.shop_url.rstrip('/')}/orders/{order_id}/payment?provider={provider.value}"


def payme_url(settings: Settings, order_id: UUID, amount_tiyin: int) -> str:
    back = result_url(settings, order_id, PaymentProvider.PAYME)
    params = f"m={settings.payme_merchant_id};ac.order_id={order_id};a={amount_tiyin};c={back}"
    encoded = base64.b64encode(params.encode()).decode()
    return f"{settings.payme_checkout_url.rstrip('/')}/{encoded}"


def click_url(settings: Settings, order_id: UUID, amount_tiyin: int) -> str:
    query = urlencode(
        {
            "service_id": settings.click_service_id,
            "merchant_id": settings.click_merchant_id,
            "amount": f"{Decimal(amount_tiyin) / TIYIN_IN_SOM:.2f}",
            "transaction_param": str(order_id),
            "return_url": result_url(settings, order_id, PaymentProvider.CLICK),
        }
    )
    return f"{settings.click_checkout_url.rstrip('/')}?{query}"


def redirect_url(
    settings: Settings, provider: PaymentProvider, order_id: UUID, amount_tiyin: int
) -> str:
    if provider is PaymentProvider.PAYME and settings.payme_checkout_url:
        return payme_url(settings, order_id, amount_tiyin)
    if provider is PaymentProvider.CLICK and settings.click_checkout_url:
        return click_url(settings, order_id, amount_tiyin)
    return result_url(settings, order_id, provider)
