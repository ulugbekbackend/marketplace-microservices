"""Payme Merchant API: every method, every error code, and repeated calls."""

from datetime import timedelta
from itertools import count
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.models import Refund, Transaction
from app.providers.payme import basic_auth, to_ms
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from contracts.enums import EventType, OrderStatus
from tests.conftest import PAYME_KEY, Clock, FakeOrders, outbox_events

URL = "/api/payments/payme/merchant"
AUTH = {"Authorization": basic_auth(PAYME_KEY)}
_ids = count(1)


async def rpc(
    client: AsyncClient,
    method: str,
    params: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request_id = next(_ids)
    response = await client.post(
        URL,
        json={"id": request_id, "method": method, "params": params},
        headers=AUTH if headers is None else headers,
    )
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["id"] == request_id
    return body


def error_code(body: dict[str, Any]) -> int:
    assert "error" in body, body
    code: int = body["error"]["code"]
    return code


def account(order_id: UUID) -> dict[str, str]:
    return {"order_id": str(order_id)}


async def create(
    client: AsyncClient, clock: Clock, order_id: UUID, amount: int, tx_id: str = "payme-tx-1"
) -> dict[str, Any]:
    return await rpc(
        client,
        "CreateTransaction",
        {"id": tx_id, "time": to_ms(clock()), "amount": amount, "account": account(order_id)},
    )


async def count_rows(sessions: async_sessionmaker[AsyncSession], model: type) -> int:
    async with sessions() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


@pytest.fixture
def order_id(orders: FakeOrders) -> UUID:
    return orders.add(amount_tiyin=1_500_000)


# --- transport and auth ---------------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": basic_auth("wrong-key")},
        {"Authorization": "Basic bm90LWJhc2U2NA==="},
        {"Authorization": "Bearer token"},
    ],
)
async def test_bad_basic_auth_is_32504(
    client: AsyncClient, order_id: UUID, headers: dict[str, str]
) -> None:
    body = await rpc(
        client,
        "CheckPerformTransaction",
        {"amount": 1_500_000, "account": account(order_id)},
        headers=headers,
    )

    assert error_code(body) == -32504
    assert set(body["error"]["message"]) == {"ru", "uz", "en"}


async def test_unknown_method_is_32601(client: AsyncClient) -> None:
    assert error_code(await rpc(client, "ChangePassword", {"password": "x"})) == -32601


async def test_invalid_json_is_32700(client: AsyncClient) -> None:
    response = await client.post(URL, content=b"{not json", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32700


async def test_missing_params_is_32600(client: AsyncClient) -> None:
    response = await client.post(URL, json={"id": 1, "method": "CheckTransaction"}, headers=AUTH)

    assert response.json()["error"]["code"] == -32600


async def test_order_service_down_is_32400(client: AsyncClient, orders: FakeOrders) -> None:
    order_id = orders.add()
    orders.mode = "down"

    body = await rpc(
        client, "CheckPerformTransaction", {"amount": 1_500_000, "account": account(order_id)}
    )

    assert error_code(body) == -32400


# --- CheckPerformTransaction ----------------------------------------------------------


async def test_check_perform_allows_a_reserved_order(client: AsyncClient, order_id: UUID) -> None:
    body = await rpc(
        client, "CheckPerformTransaction", {"amount": 1_500_000, "account": account(order_id)}
    )

    assert body["result"] == {"allow": True}


async def test_check_perform_wrong_amount_is_31001(client: AsyncClient, order_id: UUID) -> None:
    body = await rpc(
        client, "CheckPerformTransaction", {"amount": 1_000, "account": account(order_id)}
    )

    assert error_code(body) == -31001


@pytest.mark.parametrize("raw", [str(uuid4()), "not-a-uuid", None])
async def test_check_perform_unknown_order_is_31050(client: AsyncClient, raw: str | None) -> None:
    body = await rpc(
        client, "CheckPerformTransaction", {"amount": 1_500_000, "account": {"order_id": raw}}
    )

    assert error_code(body) == -31050
    assert body["error"]["data"] == "order_id"


@pytest.mark.parametrize(
    "status", [OrderStatus.PENDING, OrderStatus.EXPIRED, OrderStatus.PAID, OrderStatus.CANCELLED]
)
async def test_check_perform_not_payable_order_is_31051(
    client: AsyncClient, orders: FakeOrders, status: OrderStatus
) -> None:
    order_id = orders.add(status=status)

    body = await rpc(
        client, "CheckPerformTransaction", {"amount": 1_500_000, "account": account(order_id)}
    )

    assert error_code(body) == -31051


# --- CreateTransaction ----------------------------------------------------------------


async def test_create_transaction(
    client: AsyncClient, clock: Clock, order_id: UUID, sessions: async_sessionmaker[AsyncSession]
) -> None:
    body = await create(client, clock, order_id, 1_500_000)

    result = body["result"]
    assert result["state"] == 1
    assert result["create_time"] == to_ms(clock())
    async with sessions() as session:
        transaction = await session.scalar(select(Transaction))
    assert transaction is not None
    assert str(transaction.id) == result["transaction"]
    assert transaction.order_id == order_id
    assert transaction.amount_tiyin == 1_500_000
    assert await outbox_events(sessions) == []


async def test_repeated_create_returns_the_same_transaction(
    client: AsyncClient, clock: Clock, order_id: UUID, sessions: async_sessionmaker[AsyncSession]
) -> None:
    first = await create(client, clock, order_id, 1_500_000)
    clock.advance(timedelta(minutes=1))
    second = await create(client, clock, order_id, 1_500_000)

    assert second["result"] == first["result"]
    assert await count_rows(sessions, Transaction) == 1


async def test_second_transaction_for_the_same_order_is_refused(
    client: AsyncClient, clock: Clock, order_id: UUID
) -> None:
    await create(client, clock, order_id, 1_500_000, tx_id="payme-tx-1")

    body = await create(client, clock, order_id, 1_500_000, tx_id="payme-tx-2")

    assert error_code(body) == -31052
    assert body["error"]["data"] == "order_id"


async def test_create_wrong_amount_is_31001(
    client: AsyncClient, clock: Clock, order_id: UUID
) -> None:
    assert error_code(await create(client, clock, order_id, 999)) == -31001


async def test_create_for_an_expired_order_is_31051(
    client: AsyncClient, clock: Clock, orders: FakeOrders
) -> None:
    order_id = orders.add(status=OrderStatus.EXPIRED)

    assert error_code(await create(client, clock, order_id, 1_500_000)) == -31051


async def test_create_again_after_12_hours_cancels_with_reason_4(
    client: AsyncClient, clock: Clock, order_id: UUID
) -> None:
    await create(client, clock, order_id, 1_500_000)
    clock.advance(timedelta(hours=12, seconds=1))

    body = await create(client, clock, order_id, 1_500_000)

    assert error_code(body) == -31008
    check = await rpc(client, "CheckTransaction", {"id": "payme-tx-1"})
    assert check["result"]["state"] == -1
    assert check["result"]["reason"] == 4


# --- PerformTransaction ---------------------------------------------------------------


async def test_perform_pays_and_publishes_payment_paid(
    client: AsyncClient, clock: Clock, order_id: UUID, sessions: async_sessionmaker[AsyncSession]
) -> None:
    created = await create(client, clock, order_id, 1_500_000)
    clock.advance(timedelta(seconds=30))

    body = await rpc(client, "PerformTransaction", {"id": "payme-tx-1"})

    assert body["result"] == {
        "transaction": created["result"]["transaction"],
        "perform_time": to_ms(clock()),
        "state": 2,
    }
    events = await outbox_events(sessions)
    assert [event.event_type for event in events] == [EventType.PAYMENT_PAID.value]
    assert events[0].payload == {
        "order_id": str(order_id),
        "transaction_id": created["result"]["transaction"],
        "amount_tiyin": 1_500_000,
        "provider": "payme",
    }


async def test_repeated_perform_does_not_pay_twice(
    client: AsyncClient, clock: Clock, order_id: UUID, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await create(client, clock, order_id, 1_500_000)
    first = await rpc(client, "PerformTransaction", {"id": "payme-tx-1"})
    clock.advance(timedelta(minutes=5))

    second = await rpc(client, "PerformTransaction", {"id": "payme-tx-1"})

    assert second["result"] == first["result"]
    assert len(await outbox_events(sessions)) == 1


async def test_perform_unknown_transaction_is_31003(client: AsyncClient) -> None:
    assert error_code(await rpc(client, "PerformTransaction", {"id": "nope"})) == -31003


async def test_perform_after_12_hours_is_31008_and_cancels(
    client: AsyncClient, clock: Clock, order_id: UUID, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await create(client, clock, order_id, 1_500_000)
    clock.advance(timedelta(hours=12, minutes=1))

    body = await rpc(client, "PerformTransaction", {"id": "payme-tx-1"})

    assert error_code(body) == -31008
    check = await rpc(client, "CheckTransaction", {"id": "payme-tx-1"})
    assert (check["result"]["state"], check["result"]["reason"]) == (-1, 4)
    assert await outbox_events(sessions) == []


async def test_perform_a_cancelled_transaction_is_31008(
    client: AsyncClient, clock: Clock, order_id: UUID
) -> None:
    await create(client, clock, order_id, 1_500_000)
    await rpc(client, "CancelTransaction", {"id": "payme-tx-1", "reason": 3})

    assert error_code(await rpc(client, "PerformTransaction", {"id": "payme-tx-1"})) == -31008


# --- CancelTransaction ----------------------------------------------------------------


async def test_cancel_before_perform(
    client: AsyncClient, clock: Clock, order_id: UUID, sessions: async_sessionmaker[AsyncSession]
) -> None:
    created = await create(client, clock, order_id, 1_500_000)
    clock.advance(timedelta(seconds=10))

    body = await rpc(client, "CancelTransaction", {"id": "payme-tx-1", "reason": 3})

    assert body["result"] == {
        "transaction": created["result"]["transaction"],
        "cancel_time": to_ms(clock()),
        "state": -1,
    }
    assert await outbox_events(sessions) == []


async def test_cancel_frees_the_order_for_a_new_transaction(
    client: AsyncClient, clock: Clock, order_id: UUID
) -> None:
    await create(client, clock, order_id, 1_500_000, tx_id="payme-tx-1")
    await rpc(client, "CancelTransaction", {"id": "payme-tx-1", "reason": 3})

    body = await create(client, clock, order_id, 1_500_000, tx_id="payme-tx-2")

    assert body["result"]["state"] == 1


async def test_cancel_after_perform_refunds(
    client: AsyncClient,
    clock: Clock,
    order_id: UUID,
    orders: FakeOrders,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await create(client, clock, order_id, 1_500_000)
    await rpc(client, "PerformTransaction", {"id": "payme-tx-1"})
    orders.set_status(order_id, OrderStatus.PAID)

    body = await rpc(client, "CancelTransaction", {"id": "payme-tx-1", "reason": 5})

    assert body["result"]["state"] == -2
    events = await outbox_events(sessions)
    assert [event.event_type for event in events] == [
        EventType.PAYMENT_PAID.value,
        EventType.PAYMENT_REFUNDED.value,
    ]
    assert events[1].payload == {"order_id": str(order_id), "amount_tiyin": 1_500_000}
    assert await count_rows(sessions, Refund) == 1


async def test_repeated_cancel_returns_the_same_result(
    client: AsyncClient,
    clock: Clock,
    order_id: UUID,
    orders: FakeOrders,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await create(client, clock, order_id, 1_500_000)
    await rpc(client, "PerformTransaction", {"id": "payme-tx-1"})
    orders.set_status(order_id, OrderStatus.PAID)
    first = await rpc(client, "CancelTransaction", {"id": "payme-tx-1", "reason": 5})
    clock.advance(timedelta(minutes=1))

    second = await rpc(client, "CancelTransaction", {"id": "payme-tx-1", "reason": 5})

    assert second["result"] == first["result"]
    assert await count_rows(sessions, Refund) == 1
    assert len(await outbox_events(sessions)) == 2


async def test_cancel_a_completed_order_is_31007(
    client: AsyncClient, clock: Clock, order_id: UUID, orders: FakeOrders
) -> None:
    await create(client, clock, order_id, 1_500_000)
    await rpc(client, "PerformTransaction", {"id": "payme-tx-1"})
    orders.set_status(order_id, OrderStatus.COMPLETED)

    body = await rpc(client, "CancelTransaction", {"id": "payme-tx-1", "reason": 5})

    assert error_code(body) == -31007
    check = await rpc(client, "CheckTransaction", {"id": "payme-tx-1"})
    assert check["result"]["state"] == 2


async def test_cancel_unknown_transaction_is_31003(client: AsyncClient) -> None:
    body = await rpc(client, "CancelTransaction", {"id": "nope", "reason": 1})

    assert error_code(body) == -31003


# --- CheckTransaction and GetStatement ------------------------------------------------


async def test_check_transaction_reports_every_time(
    client: AsyncClient, clock: Clock, order_id: UUID
) -> None:
    created = await create(client, clock, order_id, 1_500_000)
    create_time = to_ms(clock())
    clock.advance(timedelta(seconds=5))
    await rpc(client, "PerformTransaction", {"id": "payme-tx-1"})

    body = await rpc(client, "CheckTransaction", {"id": "payme-tx-1"})

    assert body["result"] == {
        "create_time": create_time,
        "perform_time": to_ms(clock()),
        "cancel_time": 0,
        "transaction": created["result"]["transaction"],
        "state": 2,
        "reason": None,
    }


async def test_check_unknown_transaction_is_31003(client: AsyncClient) -> None:
    assert error_code(await rpc(client, "CheckTransaction", {"id": "nope"})) == -31003


async def test_get_statement_lists_transactions_in_the_window(
    client: AsyncClient, clock: Clock, orders: FakeOrders
) -> None:
    first_order, second_order = orders.add(), orders.add(amount_tiyin=200_000)
    start = to_ms(clock())
    await create(client, clock, first_order, 1_500_000, tx_id="payme-a")
    clock.advance(timedelta(minutes=1))
    await create(client, clock, second_order, 200_000, tx_id="payme-b")
    end = to_ms(clock())
    clock.advance(timedelta(minutes=1))
    await create(client, clock, orders.add(), 1_500_000, tx_id="payme-later")

    body = await rpc(client, "GetStatement", {"from": start, "to": end})

    statement = body["result"]["transactions"]
    assert [row["id"] for row in statement] == ["payme-a", "payme-b"]
    assert statement[1]["amount"] == 200_000
    assert statement[1]["account"] == {"order_id": str(second_order)}
    assert statement[1]["state"] == 1
