"""``search.q`` consumer: product.updated upserts the document, product.deleted removes it.

Both writes carry the event time as an external version, so a stale event is a no-op.
"""

import asyncio
import logging
from urllib.parse import urlsplit

from app.services.index import ProductIndex, epoch_millis
from contracts.enums import EventType
from contracts.events import EventEnvelope, ProductDeleted, ProductUpdated
from py_common.consumer import EventRouter, Outcome
from py_common.health import CheckFn, tcp_check
from py_common.idempotency import RedisIdempotencyStore
from py_common.rabbit import AioPikaConsumer

logger = logging.getLogger(__name__)

SERVICE = "search"


def build_router(index: ProductIndex, store: RedisIdempotencyStore) -> EventRouter:
    router = EventRouter(SERVICE, store)

    @router.on(EventType.PRODUCT_UPDATED)
    async def on_product_updated(envelope: EventEnvelope) -> None:
        product = ProductUpdated.model_validate(envelope.payload)
        await index.upsert(product, version=epoch_millis(envelope.occurred_at))

    @router.on(EventType.PRODUCT_DELETED)
    async def on_product_deleted(envelope: EventEnvelope) -> None:
        payload = ProductDeleted.model_validate(envelope.payload)
        await index.delete(payload.product_id, version=epoch_millis(envelope.occurred_at))

    return router


class ProductEventHandler:
    """What the broker consumer calls for each delivery. A failed handler releases its
    idempotency mark inside ``EventRouter``, so a retry is not taken for a duplicate."""

    def __init__(self, router: EventRouter) -> None:
        self._router = router

    async def __call__(self, body: bytes) -> Outcome:
        return await self._router.dispatch(body)


class ConsumerRunner:
    """Starts the RabbitMQ consumer in the background and keeps trying until the broker
    answers, so the HTTP API serves even while RabbitMQ is down.

    ``probe`` (a plain TCP check) runs before each attempt: aio-pika's robust connect
    swallows a cancellation that arrives mid-connect and starts reconnecting, so the
    runner only calls it once the broker port accepts connections, and shutdown never
    waits on it for longer than ``stop_timeout``.
    """

    def __init__(
        self,
        consumer: AioPikaConsumer,
        *,
        probe: CheckFn | None = None,
        retry_seconds: float = 5.0,
        stop_timeout: float = 5.0,
    ) -> None:
        self._consumer = consumer
        self._probe = probe
        self._retry_seconds = retry_seconds
        self._stop_timeout = stop_timeout
        self._task: asyncio.Task[None] | None = None
        self.started = asyncio.Event()

    def start(self) -> None:
        self._task = asyncio.create_task(self._start_loop(), name="search-consumer")

    async def _start_loop(self) -> None:
        while True:
            try:
                if self._probe is not None:
                    await self._probe()
                await self._consumer.start()
            except Exception:
                logger.warning("consumer start failed, retrying", exc_info=True)
                await self._consumer.stop()
                await asyncio.sleep(self._retry_seconds)
            else:
                self.started.set()
                return

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.wait({self._task}, timeout=self._stop_timeout)
        await self._consumer.stop()


def broker_probe(url: str) -> CheckFn:
    parts = urlsplit(url)
    return tcp_check(parts.hostname or "localhost", parts.port or 5672)
