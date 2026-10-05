"""search.q handlers: upsert, delete, duplicates, stale events and failure release."""

import asyncio
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.consumers.products import (
    ConsumerRunner,
    ProductEventHandler,
    build_router,
)
from app.services.index import IndexMissingError, ProductIndex
from pydantic import ValidationError

from contracts.events import ProductDeleted, ProductUpdated, build_event
from py_common.consumer import Outcome
from py_common.idempotency import RedisIdempotencyStore
from tests.conftest import BASE_TIME, FakeRedis, make_product


def updated(product: ProductUpdated, at: datetime, event_id: UUID | None = None) -> bytes:
    envelope = build_event(
        product, producer="catalog", correlation_id=uuid4(), occurred_at=at, event_id=event_id
    )
    return envelope.model_dump_json().encode()


def deleted(product_id: UUID, at: datetime) -> bytes:
    envelope = build_event(
        ProductDeleted(product_id=product_id),
        producer="catalog",
        correlation_id=uuid4(),
        occurred_at=at,
    )
    return envelope.model_dump_json().encode()


@pytest.fixture
def handler(index: ProductIndex, redis: FakeRedis) -> ProductEventHandler:
    store = RedisIdempotencyStore(redis, prefix="search")
    return ProductEventHandler(build_router(index, store))


async def source_of(index: ProductIndex, product_id: UUID) -> dict[str, Any] | None:
    response = await index.es.options(ignore_status=404).get(index=index.alias, id=str(product_id))
    if not response.body.get("found"):
        return None
    source: dict[str, Any] = response.body["_source"]
    return source


async def test_product_updated_is_indexed(
    handler: ProductEventHandler, index: ProductIndex
) -> None:
    await index.ensure()
    product = make_product(title="Telefon")

    assert await handler(updated(product, BASE_TIME)) is Outcome.HANDLED

    source = await source_of(index, product.product_id)
    assert source is not None
    assert source["title"] == "Telefon"


async def test_newer_update_replaces_the_document(
    handler: ProductEventHandler, index: ProductIndex
) -> None:
    await index.ensure()
    product = make_product(title="Old")
    await handler(updated(product, BASE_TIME))

    newer = product.model_copy(update={"title": "New", "min_price_tiyin": 1})
    await handler(updated(newer, BASE_TIME + timedelta(seconds=1)))

    source = await source_of(index, product.product_id)
    assert source is not None
    assert (source["title"], source["min_price"]) == ("New", 1)


async def test_stale_update_is_ignored(handler: ProductEventHandler, index: ProductIndex) -> None:
    await index.ensure()
    product = make_product(title="Current")
    await handler(updated(product, BASE_TIME))

    older = product.model_copy(update={"title": "Outdated"})
    outcome = await handler(updated(older, BASE_TIME - timedelta(seconds=1)))

    assert outcome is Outcome.HANDLED  # acknowledged, not retried
    source = await source_of(index, product.product_id)
    assert source is not None
    assert source["title"] == "Current"


async def test_duplicate_event_is_handled_once(
    handler: ProductEventHandler, index: ProductIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    await index.ensure()
    body = updated(make_product(), BASE_TIME, event_id=uuid4())
    calls = 0
    original = index.upsert

    async def counting(product: ProductUpdated, *, version: int) -> bool:
        nonlocal calls
        calls += 1
        return await original(product, version=version)

    monkeypatch.setattr(index, "upsert", counting)

    assert await handler(body) is Outcome.HANDLED
    assert await handler(body) is Outcome.DUPLICATE
    assert calls == 1


async def test_product_deleted_removes_the_document(
    handler: ProductEventHandler, index: ProductIndex
) -> None:
    await index.ensure()
    product = make_product()
    await handler(updated(product, BASE_TIME))

    assert await handler(deleted(product.product_id, BASE_TIME + timedelta(seconds=1))) is (
        Outcome.HANDLED
    )
    assert await source_of(index, product.product_id) is None


async def test_stale_delete_is_ignored(handler: ProductEventHandler, index: ProductIndex) -> None:
    await index.ensure()
    product = make_product()
    await handler(updated(product, BASE_TIME))

    await handler(deleted(product.product_id, BASE_TIME - timedelta(seconds=1)))

    assert await source_of(index, product.product_id) is not None


async def test_failed_event_can_be_retried(
    handler: ProductEventHandler, index: ProductIndex, redis: FakeRedis
) -> None:
    body = updated(make_product(), BASE_TIME)

    with pytest.raises(IndexMissingError):
        await handler(body)  # no index yet
    assert redis.data == {}  # the mark was released

    await index.ensure()
    assert await handler(body) is Outcome.HANDLED


async def test_malformed_message_is_rejected(handler: ProductEventHandler) -> None:
    with pytest.raises(ValidationError):
        await handler(b'{"not": "an envelope"}')


async def test_malformed_payload_is_rejected_and_released(
    handler: ProductEventHandler, redis: FakeRedis, index: ProductIndex
) -> None:
    envelope = build_event(
        make_product(), producer="catalog", correlation_id=uuid4(), occurred_at=BASE_TIME
    )
    broken = envelope.model_copy(update={"payload": {"product_id": "nope"}})

    with pytest.raises(ValidationError):
        await handler(broken.model_dump_json().encode())
    assert redis.data == {}


async def test_other_events_are_ignored(handler: ProductEventHandler) -> None:
    from contracts.events import SellerApproved

    body = build_event(
        SellerApproved(user_id=uuid4(), shop_name="Shop"),
        producer="auth",
        correlation_id=uuid4(),
        occurred_at=BASE_TIME,
    )

    assert await handler(body.model_dump_json().encode()) is Outcome.IGNORED


class FlakyConsumer:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.starts = 0
        self.stops = 0

    async def start(self) -> None:
        self.starts += 1
        if self.starts <= self.failures:
            raise ConnectionError("broker down")

    async def stop(self) -> None:
        self.stops += 1


async def test_runner_retries_until_the_broker_answers() -> None:
    consumer = FlakyConsumer(failures=2)
    runner = ConsumerRunner(consumer, retry_seconds=0.01)  # type: ignore[arg-type]

    runner.start()
    await asyncio.wait_for(runner.started.wait(), timeout=2)
    await runner.stop()

    assert consumer.starts == 3
    assert consumer.stops == 3  # two failed attempts cleaned up + shutdown


async def test_runner_stop_cancels_a_pending_start() -> None:
    consumer = FlakyConsumer(failures=1_000)
    runner = ConsumerRunner(consumer, retry_seconds=10)  # type: ignore[arg-type]

    runner.start()
    await asyncio.sleep(0.05)
    await runner.stop()

    assert not runner.started.is_set()
    assert consumer.starts == 1
