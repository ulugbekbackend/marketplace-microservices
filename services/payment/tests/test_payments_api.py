"""Customer API: start a payment (redirect URL) and the development mock payment."""

import base64
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from app.core.config import Settings
from app.services import checkout
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from contracts.enums import EventType, OrderStatus, PaymentProvider
from tests.conftest import FakeOrders, outbox_events, user_headers
from tests.test_click import prepare_form


@pytest.fixture
def customer_id() -> UUID:
    return uuid4()


@pytest.fixture
def order_id(orders: FakeOrders, customer_id: UUID) -> UUID:
    return orders.add(amount_tiyin=2_500_000, customer_id=customer_id)


# --- init -----------------------------------------------------------------------------


@pytest.mark.parametrize("provider", ["payme", "click"])
async def test_init_without_checkout_goes_to_the_result_page(
    client: AsyncClient, order_id: UUID, customer_id: UUID, provider: str
) -> None:
    response = await client.post(
        f"/api/payments/{order_id}/init/",
        json={"provider": provider},
        headers=user_headers(customer_id),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "redirect_url": f"http://shop.test/orders/{order_id}/payment?provider={provider}"
    }


async def test_init_requires_authentication(client: AsyncClient, order_id: UUID) -> None:
    response = await client.post(f"/api/payments/{order_id}/init/", json={"provider": "payme"})

    assert response.status_code == 401


async def test_init_for_someone_elses_order_is_404(client: AsyncClient, order_id: UUID) -> None:
    response = await client.post(
        f"/api/payments/{order_id}/init/",
        json={"provider": "payme"},
        headers=user_headers(uuid4()),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_init_for_an_unknown_order_is_404(client: AsyncClient, customer_id: UUID) -> None:
    response = await client.post(
        f"/api/payments/{uuid4()}/init/",
        json={"provider": "payme"},
        headers=user_headers(customer_id),
    )

    assert response.status_code == 404


async def test_init_for_a_not_payable_order_is_409(
    client: AsyncClient, orders: FakeOrders, customer_id: UUID
) -> None:
    order_id = orders.add(status=OrderStatus.EXPIRED, customer_id=customer_id)

    response = await client.post(
        f"/api/payments/{order_id}/init/",
        json={"provider": "click"},
        headers=user_headers(customer_id),
    )

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "ORDER_NOT_PAYABLE",
        "message": "This order cannot be paid.",
        "details": {"status": "EXPIRED"},
    }


async def test_init_rejects_the_mock_provider(
    client: AsyncClient, order_id: UUID, customer_id: UUID
) -> None:
    response = await client.post(
        f"/api/payments/{order_id}/init/",
        json={"provider": "mock"},
        headers=user_headers(customer_id),
    )

    assert response.status_code == 400


async def test_init_while_orders_are_down_is_503(
    client: AsyncClient, orders: FakeOrders, order_id: UUID, customer_id: UUID
) -> None:
    orders.mode = "error"

    response = await client.post(
        f"/api/payments/{order_id}/init/",
        json={"provider": "payme"},
        headers=user_headers(customer_id),
    )

    assert response.status_code == 503


def test_payme_checkout_url(settings: Settings) -> None:
    configured = replace(settings, payme_checkout_url="https://checkout.paycom.uz/")
    order_id = uuid4()

    url = checkout.redirect_url(configured, PaymentProvider.PAYME, order_id, 2_500_000)

    prefix = "https://checkout.paycom.uz/"
    assert url.startswith(prefix)
    decoded = base64.b64decode(url.removeprefix(prefix)).decode()
    assert decoded == (
        f"m=merchant-1;ac.order_id={order_id};a=2500000;"
        f"c=http://shop.test/orders/{order_id}/payment?provider=payme"
    )


def test_click_checkout_url(settings: Settings) -> None:
    configured = replace(settings, click_checkout_url="https://my.click.uz/services/pay")
    order_id = uuid4()

    url = checkout.redirect_url(configured, PaymentProvider.CLICK, order_id, 2_500_050)

    parts = urlsplit(url)
    query = {key: values[0] for key, values in parse_qs(parts.query).items()}
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://my.click.uz/services/pay"
    assert query == {
        "service_id": "777",
        "merchant_id": "click-merchant",
        "amount": "25000.50",
        "transaction_param": str(order_id),
        "return_url": f"http://shop.test/orders/{order_id}/payment?provider=click",
    }


# --- mock -----------------------------------------------------------------------------


async def test_mock_pay_publishes_payment_paid(
    client: AsyncClient,
    order_id: UUID,
    customer_id: UUID,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    response = await client.post(
        f"/api/payments/mock/{order_id}/pay", headers=user_headers(customer_id)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["order_id"] == str(order_id)
    assert body["amount_tiyin"] == 2_500_000
    events = await outbox_events(sessions)
    assert [event.event_type for event in events] == [EventType.PAYMENT_PAID.value]
    assert events[0].payload == {
        "order_id": str(order_id),
        "transaction_id": body["transaction_id"],
        "amount_tiyin": 2_500_000,
        "provider": "mock",
    }


async def test_mock_pay_is_404_when_disabled(
    app: FastAPI, client: AsyncClient, order_id: UUID, customer_id: UUID, settings: Settings
) -> None:
    app.state.settings = replace(settings, mock_enabled=False)

    response = await client.post(
        f"/api/payments/mock/{order_id}/pay", headers=user_headers(customer_id)
    )

    assert response.status_code == 404


async def test_mock_pay_for_someone_elses_order_is_404(client: AsyncClient, order_id: UUID) -> None:
    response = await client.post(
        f"/api/payments/mock/{order_id}/pay", headers=user_headers(uuid4())
    )

    assert response.status_code == 404


async def test_mock_pay_while_a_provider_transaction_is_open_is_409(
    client: AsyncClient, order_id: UUID, customer_id: UUID
) -> None:
    prepared = await client.post(
        "/api/payments/click/prepare",
        data=prepare_form(order_id, amount="25000.00"),
    )
    assert prepared.json()["error"] == 0

    response = await client.post(
        f"/api/payments/mock/{order_id}/pay", headers=user_headers(customer_id)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PAYMENT_IN_PROGRESS"
