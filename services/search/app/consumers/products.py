"""``search.q`` consumer: product.updated upserts the document, product.deleted removes it.

Both writes carry the event time as an external version, so a stale event is a no-op.
"""

import logging

from app.services.index import ProductIndex, epoch_millis
from contracts.enums import EventType
from contracts.events import EventEnvelope, ProductDeleted, ProductUpdated
from py_common.consumer import EventRouter, Outcome
from py_common.idempotency import RedisIdempotencyStore

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
