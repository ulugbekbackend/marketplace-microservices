"""Outbox relay, the order client, concurrent webhooks and the migrations."""

import asyncio
from typing import Any
from uuid import uuid4

import httpx
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.models import Base
from app.outbox import OutboxRelay, add_event, publish_pending
from app.services.orders import OrderClient, OrderUnavailableError
from httpx import AsyncClient
from prometheus_client import REGISTRY
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from contracts.enums import EventType, PaymentProvider
from contracts.events import EventEnvelope, PaymentPaid
from py_common.context import request_context
from tests.conftest import FakeOrders, outbox_events
from tests.test_click import PREPARE, prepare_form
from tests.test_payme import create, rpc


class RecordingPublisher:
    def __init__(self, *, fail_after: int | None = None) -> None:
        self.published: list[EventEnvelope] = []
        self._fail_after = fail_after

    async def publish(self, envelope: EventEnvelope) -> None:
        if self._fail_after is not None and len(self.published) >= self._fail_after:
            raise ConnectionError("broker down")
        self.published.append(envelope)


def paid() -> PaymentPaid:
    return PaymentPaid(
        order_id=uuid4(), transaction_id=uuid4(), amount_tiyin=100, provider=PaymentProvider.MOCK
    )


async def stage(sessions: async_sessionmaker[AsyncSession], n: int) -> None:
    async with sessions.begin() as session:
        for _ in range(n):
            add_event(session, paid())


async def test_events_carry_the_request_correlation_id(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    with request_context() as (correlation_id, _):
        await stage(sessions, 1)

    publisher = RecordingPublisher()
    assert await publish_pending(sessions, publisher) == 1
    envelope = publisher.published[0]
    assert envelope.correlation_id == correlation_id
    assert envelope.producer == "payment"
    assert envelope.event_type is EventType.PAYMENT_PAID


async def test_published_rows_are_stamped_and_not_sent_again(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await stage(sessions, 3)
    publisher = RecordingPublisher()

    assert await publish_pending(sessions, publisher) == 3
    assert await publish_pending(sessions, publisher) == 0
    assert len(publisher.published) == 3
    assert all(row.published_at is not None for row in await outbox_events(sessions))


async def test_a_broker_failure_keeps_the_rest_for_later(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await stage(sessions, 3)

    assert await publish_pending(sessions, RecordingPublisher(fail_after=1)) == 1

    retry = RecordingPublisher()
    assert await publish_pending(sessions, retry) == 2
    rows = await outbox_events(sessions)
    assert [envelope.event_id for envelope in retry.published] == [r.event_id for r in rows[1:]]


async def test_relay_publishes_in_the_background(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    publisher = RecordingPublisher()
    relay = OutboxRelay(sessions, publisher, interval=0.01)
    relay.start()
    try:
        await stage(sessions, 2)
        for _ in range(200):
            if len(publisher.published) == 2:
                break
            await asyncio.sleep(0.01)
    finally:
        await relay.stop()

    assert len(publisher.published) == 2


async def test_relay_keeps_going_after_database_errors(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    attempts = 0

    def flaky() -> Any:
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise ConnectionError("database is restarting")
        return sessions.begin()

    flaky_sessions = type("Flaky", (), {"begin": staticmethod(flaky)})()
    publisher = RecordingPublisher()
    relay = OutboxRelay(flaky_sessions, publisher, interval=0.01)
    await stage(sessions, 1)
    relay.start()
    try:
        for _ in range(300):
            if publisher.published:
                break
            await asyncio.sleep(0.01)
    finally:
        await relay.stop()

    assert attempts >= 3
    assert len(publisher.published) == 1


# --- order client ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "response",
    [httpx.Response(500), httpx.Response(200, json={"unexpected": True}), httpx.Response(200)],
)
async def test_order_client_rejects_bad_answers(response: httpx.Response) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    async with httpx.AsyncClient(
        base_url="http://order.test", transport=httpx.MockTransport(handler)
    ) as http:
        with pytest.raises(OrderUnavailableError):
            await OrderClient(http).payable(uuid4())


async def test_order_client_maps_404_to_none(orders: FakeOrders) -> None:
    async with httpx.AsyncClient(
        base_url="http://order.test", transport=httpx.MockTransport(orders.handler)
    ) as http:
        assert await OrderClient(http).payable(uuid4()) is None


# --- concurrency ----------------------------------------------------------------------


async def test_concurrent_performs_pay_once(
    client: AsyncClient, clock: Any, orders: FakeOrders, sessions: async_sessionmaker[AsyncSession]
) -> None:
    order_id = orders.add()
    await create(client, clock, order_id, 1_500_000)

    answers = await asyncio.gather(
        *(rpc(client, "PerformTransaction", {"id": "payme-tx-1"}) for _ in range(5))
    )

    assert {answer["result"]["state"] for answer in answers} == {2}
    assert len({answer["result"]["perform_time"] for answer in answers}) == 1
    assert len(await outbox_events(sessions)) == 1


async def test_concurrent_creates_keep_one_transaction(
    client: AsyncClient, clock: Any, orders: FakeOrders
) -> None:
    order_id = orders.add()

    answers = await asyncio.gather(
        *(create(client, clock, order_id, 1_500_000, tx_id=f"payme-{i}") for i in range(4))
    )

    created = [answer for answer in answers if "result" in answer]
    refused = [answer for answer in answers if "error" in answer]
    assert len(created) == 1
    assert {answer["error"]["code"] for answer in refused} == {-31052}


# --- migrations -----------------------------------------------------------------------


async def test_migrations_match_the_models(engine: AsyncEngine) -> None:
    def diff(connection: Any) -> list[Any]:
        changes: list[Any] = compare_metadata(MigrationContext.configure(connection), Base.metadata)
        return changes

    async with engine.connect() as connection:
        assert await connection.run_sync(diff) == []


# --- metrics --------------------------------------------------------------------------


def errors(provider: str, code: str) -> float:
    return (
        REGISTRY.get_sample_value("payment_errors_total", {"provider": provider, "code": code})
        or 0.0
    )


async def test_provider_errors_are_counted(client: AsyncClient, orders: FakeOrders) -> None:
    payme_before, click_before = errors("payme", "-31050"), errors("click", "-5")

    await rpc(
        client, "CheckPerformTransaction", {"amount": 100, "account": {"order_id": str(uuid4())}}
    )
    await client.post(PREPARE, data=prepare_form(uuid4()))

    assert errors("payme", "-31050") == payme_before + 1
    assert errors("click", "-5") == click_before + 1
