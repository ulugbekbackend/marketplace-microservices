"""Click SHOP API: prepare / complete, the signature and every error code."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from app.models import Transaction, TransactionState
from app.providers.click import sign
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from contracts.enums import EventType, OrderStatus
from tests.conftest import CLICK_SECRET, CLICK_SERVICE_ID, FakeOrders, outbox_events

PREPARE = "/api/payments/click/prepare"
COMPLETE = "/api/payments/click/complete"


def prepare_form(
    order_id: UUID | str, amount: str = "15000.00", **overrides: str
) -> dict[str, str]:
    form = {
        "click_trans_id": "5001",
        "service_id": CLICK_SERVICE_ID,
        "click_paydoc_id": "9001",
        "merchant_trans_id": str(order_id),
        "amount": amount,
        "action": "0",
        "error": "0",
        "error_note": "Success",
        "sign_time": "2026-10-09 12:00:00",
    }
    form.update(overrides)
    form["sign_string"] = sign(form, CLICK_SECRET, with_prepare_id=False)
    return form


def complete_form(
    order_id: UUID | str, prepare_id: int, amount: str = "15000.00", **overrides: str
) -> dict[str, str]:
    form = prepare_form(order_id, amount)
    form.update({"action": "1", "merchant_prepare_id": str(prepare_id)})
    form.update(overrides)
    form["sign_string"] = sign(form, CLICK_SECRET, with_prepare_id=True)
    return form


async def post(client: AsyncClient, url: str, form: dict[str, str]) -> dict[str, Any]:
    response = await client.post(url, data=form)
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


@pytest.fixture
def order_id(orders: FakeOrders) -> UUID:
    return orders.add(amount_tiyin=1_500_000)


async def test_prepare_then_complete_pays(
    client: AsyncClient, order_id: UUID, sessions: async_sessionmaker[AsyncSession]
) -> None:
    prepared = await post(client, PREPARE, prepare_form(order_id))

    assert prepared == {
        "click_trans_id": 5001,
        "merchant_trans_id": str(order_id),
        "merchant_prepare_id": prepared["merchant_prepare_id"],
        "error": 0,
        "error_note": "Success",
    }
    completed = await post(
        client, COMPLETE, complete_form(order_id, prepared["merchant_prepare_id"])
    )
    assert completed["error"] == 0
    assert completed["merchant_confirm_id"] == prepared["merchant_prepare_id"]
    events = await outbox_events(sessions)
    assert [event.event_type for event in events] == [EventType.PAYMENT_PAID.value]
    assert events[0].payload["provider"] == "click"
    assert events[0].payload["amount_tiyin"] == 1_500_000


async def test_repeated_prepare_returns_the_same_prepare_id(
    client: AsyncClient, order_id: UUID
) -> None:
    first = await post(client, PREPARE, prepare_form(order_id))
    second = await post(client, PREPARE, prepare_form(order_id))

    assert second["error"] == 0
    assert second["merchant_prepare_id"] == first["merchant_prepare_id"]


async def test_repeated_complete_is_already_paid_and_pays_once(
    client: AsyncClient, order_id: UUID, sessions: async_sessionmaker[AsyncSession]
) -> None:
    prepared = await post(client, PREPARE, prepare_form(order_id))
    form = complete_form(order_id, prepared["merchant_prepare_id"])
    await post(client, COMPLETE, form)

    again = await post(client, COMPLETE, form)

    assert again["error"] == -4
    assert len(await outbox_events(sessions)) == 1


@pytest.mark.parametrize("url", [PREPARE, COMPLETE])
async def test_bad_signature_is_minus_1(client: AsyncClient, order_id: UUID, url: str) -> None:
    form = prepare_form(order_id) if url == PREPARE else complete_form(order_id, 1)
    form["sign_string"] = "0" * 32

    assert (await post(client, url, form))["error"] == -1


async def test_tampered_amount_breaks_the_signature(client: AsyncClient, order_id: UUID) -> None:
    form = prepare_form(order_id)
    form["amount"] = "1.00"

    assert (await post(client, PREPARE, form))["error"] == -1


async def test_prepare_wrong_amount_is_minus_2(client: AsyncClient, order_id: UUID) -> None:
    body = await post(client, PREPARE, prepare_form(order_id, amount="14999.99"))

    assert body["error"] == -2


async def test_complete_wrong_amount_is_minus_2(client: AsyncClient, order_id: UUID) -> None:
    prepared = await post(client, PREPARE, prepare_form(order_id))

    body = await post(
        client,
        COMPLETE,
        complete_form(order_id, prepared["merchant_prepare_id"], amount="100.00"),
    )

    assert body["error"] == -2


async def test_wrong_action_is_minus_3(client: AsyncClient, order_id: UUID) -> None:
    body = await post(client, PREPARE, prepare_form(order_id, action="1"))

    assert body["error"] == -3


async def test_prepare_for_a_paid_order_is_minus_4(client: AsyncClient, orders: FakeOrders) -> None:
    order_id = orders.add(status=OrderStatus.PAID)

    assert (await post(client, PREPARE, prepare_form(order_id)))["error"] == -4


@pytest.mark.parametrize("merchant_trans_id", [str(uuid4()), "not-a-uuid"])
async def test_unknown_order_is_minus_5(client: AsyncClient, merchant_trans_id: str) -> None:
    body = await post(client, PREPARE, prepare_form(merchant_trans_id))

    assert body["error"] == -5


async def test_complete_unknown_transaction_is_minus_6(client: AsyncClient, order_id: UUID) -> None:
    assert (await post(client, COMPLETE, complete_form(order_id, 424242)))["error"] == -6


async def test_complete_with_another_prepare_id_is_minus_6(
    client: AsyncClient, order_id: UUID
) -> None:
    prepared = await post(client, PREPARE, prepare_form(order_id))

    body = await post(
        client, COMPLETE, complete_form(order_id, prepared["merchant_prepare_id"] + 100)
    )

    assert body["error"] == -6


async def test_missing_field_is_minus_8(client: AsyncClient, order_id: UUID) -> None:
    form = prepare_form(order_id)
    del form["sign_time"]

    assert (await post(client, PREPARE, form))["error"] == -8


async def test_click_failure_on_complete_cancels_with_minus_9(
    client: AsyncClient, order_id: UUID, sessions: async_sessionmaker[AsyncSession]
) -> None:
    prepared = await post(client, PREPARE, prepare_form(order_id))
    prepare_id = prepared["merchant_prepare_id"]

    body = await post(client, COMPLETE, complete_form(order_id, prepare_id, error="-5017"))

    assert body["error"] == -9
    async with sessions() as session:
        transaction = await session.scalar(select(Transaction))
    assert transaction is not None
    assert transaction.state == TransactionState.CANCELLED
    assert await outbox_events(sessions) == []
    again = await post(client, COMPLETE, complete_form(order_id, prepare_id))
    assert again["error"] == -9


async def test_prepare_for_an_expired_order_is_minus_9(
    client: AsyncClient, orders: FakeOrders
) -> None:
    order_id = orders.add(status=OrderStatus.EXPIRED)

    assert (await post(client, PREPARE, prepare_form(order_id)))["error"] == -9


async def test_prepare_while_another_transaction_is_open_is_minus_9(
    client: AsyncClient, order_id: UUID
) -> None:
    await post(client, PREPARE, prepare_form(order_id))

    body = await post(client, PREPARE, prepare_form(order_id, click_trans_id="5002"))

    assert body["error"] == -9


async def test_order_service_down_is_minus_8(client: AsyncClient, orders: FakeOrders) -> None:
    order_id = orders.add()
    orders.mode = "down"

    assert (await post(client, PREPARE, prepare_form(order_id)))["error"] == -8
