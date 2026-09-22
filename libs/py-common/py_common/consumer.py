"""Broker independent consumer core: parse, drop duplicates, route to a handler.

The aio-pika / pika wiring lives in the services; this part is what needs tests.
"""

import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum

from contracts.enums import EventType
from contracts.events import EventEnvelope
from py_common.context import request_context
from py_common.idempotency import IdempotencyStore

logger = logging.getLogger(__name__)

Handler = Callable[[EventEnvelope], Awaitable[None]]


class Outcome(StrEnum):
    HANDLED = "handled"
    DUPLICATE = "duplicate"
    IGNORED = "ignored"


class EventRouter:
    """Maps event types to handlers and enforces once only processing."""

    def __init__(self, service: str, store: IdempotencyStore) -> None:
        self.service = service
        self._store = store
        self._handlers: dict[EventType, Handler] = {}

    def on(self, event_type: EventType) -> Callable[[Handler], Handler]:
        def register(handler: Handler) -> Handler:
            if event_type in self._handlers:
                raise ValueError(f"handler for {event_type} already registered")
            self._handlers[event_type] = handler
            return handler

        return register

    @property
    def handled_types(self) -> frozenset[EventType]:
        return frozenset(self._handlers)

    async def dispatch(self, raw: bytes | str) -> Outcome:
        """Handle one delivery. Raising means the caller should retry or dead letter it."""
        envelope = EventEnvelope.model_validate_json(raw)
        handler = self._handlers.get(envelope.event_type)
        if handler is None:
            logger.debug("no handler", extra={"event_type": str(envelope.event_type)})
            return Outcome.IGNORED

        with request_context(correlation_id=envelope.correlation_id):
            if not await self._store.mark_processed(envelope.event_id):
                logger.info("duplicate event", extra={"event_id": str(envelope.event_id)})
                return Outcome.DUPLICATE
            await handler(envelope)
            return Outcome.HANDLED
