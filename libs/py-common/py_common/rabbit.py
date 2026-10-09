"""RabbitMQ wiring: a confirming publisher for outbox relays, and consumers that retry a
failed message with growing delays and dead letter it after the last attempt.

Django services use the blocking (pika) side, FastAPI services the asyncio (aio-pika) side.
Both share the failure policy below, which is where the behaviour lives.
"""

import asyncio
import logging
import signal
import threading
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import aio_pika
import pika
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractIncomingMessage,
    AbstractRobustConnection,
)
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import AMQPError
from pydantic import ValidationError

from contracts.enums import EventType
from contracts.events import EventEnvelope
from contracts.topology import EXCHANGE, dlq_name, queue_name, retry_queue_name
from py_common.context import request_context
from py_common.health import CheckFn, tcp_check
from py_common.retry import RETRY_COUNT_HEADER, DeadLetter, RetryPolicy, attempt_from_headers

logger = logging.getLogger(__name__)

ERROR_HEADER = "x-last-error"
_ERROR_MAX_LENGTH = 500


class PermanentError(Exception):
    """Retrying cannot help (malformed message, broken invariant): dead letter at once."""


# --- failure policy -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Redirect:
    """Where a failed message goes next: the retry queue (with a delay) or the DLQ."""

    queue: str
    headers: dict[str, Any]
    expiration_ms: int | None


def redirect_failed(
    service: str,
    headers: Mapping[str, Any] | None,
    error: BaseException,
    policy: RetryPolicy,
) -> Redirect:
    """Decide the next stop of a message whose handler raised ``error``."""
    attempt = attempt_from_headers(dict(headers) if headers else None)
    permanent = isinstance(error, PermanentError | ValidationError)
    decision = DeadLetter(attempts=attempt) if permanent else policy.decide(attempt)
    new_headers = {
        # The broker's own dead lettering bookkeeping is not ours to copy forward.
        **{key: value for key, value in (headers or {}).items() if not _is_broker_header(key)},
        ERROR_HEADER: f"{type(error).__name__}: {error}"[:_ERROR_MAX_LENGTH],
    }
    if isinstance(decision, DeadLetter):
        new_headers[RETRY_COUNT_HEADER] = attempt
        return Redirect(dlq_name(service), new_headers, None)
    new_headers[RETRY_COUNT_HEADER] = decision.attempt
    return Redirect(retry_queue_name(service), new_headers, decision.delay_ms)


def _is_broker_header(key: str) -> bool:
    return key.startswith(("x-death", "x-first-death", "x-last-death"))


# --- dispatch -----------------------------------------------------------------------------

SyncHandler = Callable[[EventEnvelope], object]


def make_dispatch(handlers: Mapping[EventType, SyncHandler]) -> Callable[[bytes], None]:
    """Turn a handler table into the ``handle(body)`` a blocking consumer calls.

    Handlers own their transaction and their processed-events check: the dedup row has
    to commit together with the change it guards.
    """

    def dispatch(body: bytes) -> None:
        envelope = EventEnvelope.model_validate_json(body)
        handler = handlers.get(envelope.event_type)
        if handler is None:
            logger.info("no handler", extra={"event_type": str(envelope.event_type)})
            return
        with request_context(correlation_id=envelope.correlation_id):
            handler(envelope)

    return dispatch


# --- blocking side (pika) -----------------------------------------------------------------


def connection_parameters(url: str) -> pika.URLParameters:
    params = pika.URLParameters(url)
    params.heartbeat = 30
    params.blocked_connection_timeout = 30
    params.connection_attempts = 3
    params.retry_delay = 2
    return params


def envelope_properties(envelope: EventEnvelope) -> pika.BasicProperties:
    return pika.BasicProperties(
        content_type="application/json",
        delivery_mode=pika.DeliveryMode.Persistent,
        message_id=str(envelope.event_id),
        correlation_id=str(envelope.correlation_id),
        type=str(envelope.event_type),
        timestamp=int(envelope.occurred_at.timestamp()),
        app_id=envelope.producer,
    )


class PikaPublisher:
    """``py_common.outbox.Publisher`` over a blocking connection with publisher confirms.

    ``publish`` returns only after the broker confirmed the message, and raises otherwise,
    so the outbox row stays unpublished. The connection is opened lazily and rebuilt after
    an error.
    """

    def __init__(self, url: str, *, exchange: str = EXCHANGE) -> None:
        self._params = connection_parameters(url)
        self._exchange = exchange
        self._connection: pika.BlockingConnection | None = None
        self._channel: BlockingChannel | None = None

    def _ensure_channel(self) -> BlockingChannel:
        if self._channel is None or not self._channel.is_open:
            self.close()
            self._connection = pika.BlockingConnection(self._params)
            self._channel = self._connection.channel()
            self._channel.confirm_delivery()
        return self._channel

    def publish(self, envelope: EventEnvelope) -> None:
        reused = self._channel is not None and self._channel.is_open
        try:
            self._publish(envelope)
        except AMQPError:
            self.close()
            if not reused:
                raise
            # The broker may have dropped a connection that pika still reports open.
            logger.info("broker connection went stale, reconnecting")
            try:
                self._publish(envelope)
            except AMQPError:
                self.close()
                raise

    def _publish(self, envelope: EventEnvelope) -> None:
        self._ensure_channel().basic_publish(
            exchange=self._exchange,
            routing_key=str(envelope.event_type),
            body=envelope.model_dump_json().encode(),
            properties=envelope_properties(envelope),
        )

    def idle(self, seconds: float) -> None:
        """Wait while answering broker heartbeats.

        A blocking connection only does I/O when called, so without this an idle relay
        misses heartbeats and the broker drops the connection.
        """
        connection = self._connection
        if connection is None or not connection.is_open:
            time.sleep(seconds)
            return
        try:
            connection.sleep(seconds)
        except AMQPError:
            self.close()

    def close(self) -> None:
        connection, self._connection, self._channel = self._connection, None, None
        if connection is not None and connection.is_open:
            try:
                connection.close()
            except AMQPError:
                logger.debug("closing a broken connection failed", exc_info=True)


def run_relay(
    publish_batch: Callable[[], int],
    stop: threading.Event,
    *,
    interval: float = 1.0,
    idle: Callable[[float], object] | None = None,
) -> None:
    """Drain the outbox until ``stop`` is set. Sleeps only when a batch came back empty.

    ``idle`` replaces the plain wait, e.g. ``PikaPublisher.idle`` to keep the connection
    alive between batches.
    """
    wait = idle or stop.wait
    while not stop.is_set():
        try:
            published = publish_batch()
        except Exception:
            logger.exception("outbox relay batch failed")
            published = 0
        if published == 0:
            wait(interval)


def stop_on_signals() -> threading.Event:
    """An event that SIGTERM / SIGINT set, for graceful shutdown of a worker loop."""
    stop = threading.Event()

    def _set(signum: int, _frame: object) -> None:
        logger.info("stopping", extra={"signal": signum})
        stop.set()

    signal.signal(signal.SIGTERM, _set)
    signal.signal(signal.SIGINT, _set)
    return stop


class BlockingConsumer:
    """Consumes ``<service>.q``. A handler error sends the message to the retry queue
    (it comes back after the delay) or, once attempts are used up, to the DLQ.

    The original delivery is acked only after the redirected copy is confirmed, so a
    crash in between means a redelivery, never a loss.
    """

    def __init__(
        self,
        url: str,
        service: str,
        handle: Callable[[bytes], object],
        *,
        policy: RetryPolicy | None = None,
        prefetch: int = 10,
    ) -> None:
        self._params = connection_parameters(url)
        self.service = service
        self._handle = handle
        self._policy = policy or RetryPolicy()
        self._prefetch = prefetch

    def run(self, stop: threading.Event, *, reconnect_delay: float = 5.0) -> None:
        while not stop.is_set():
            try:
                self._consume(stop)
            except AMQPError:
                logger.exception("consumer connection lost, reconnecting")
                stop.wait(reconnect_delay)

    def _consume(self, stop: threading.Event) -> None:
        connection = pika.BlockingConnection(self._params)
        try:
            channel = connection.channel()
            channel.confirm_delivery()
            channel.basic_qos(prefetch_count=self._prefetch)
            logger.info("consuming", extra={"queue": queue_name(self.service)})
            for method, properties, body in channel.consume(
                queue_name(self.service), inactivity_timeout=1
            ):
                if stop.is_set():
                    break
                if method is None:
                    continue
                self.process(channel, method.delivery_tag, properties, body)
            channel.cancel()
        finally:
            if connection.is_open:
                connection.close()

    def process(
        self,
        channel: BlockingChannel,
        delivery_tag: int,
        properties: pika.BasicProperties,
        body: bytes,
    ) -> None:
        try:
            self._handle(body)
        except Exception as error:
            target = redirect_failed(self.service, properties.headers, error, self._policy)
            log = logger.error if target.queue == dlq_name(self.service) else logger.warning
            log(
                "event handling failed",
                exc_info=True,
                extra={"message_id": properties.message_id, "next_queue": target.queue},
            )
            channel.basic_publish(
                exchange="",
                routing_key=target.queue,
                body=body,
                properties=pika.BasicProperties(
                    content_type=properties.content_type,
                    delivery_mode=pika.DeliveryMode.Persistent,
                    message_id=properties.message_id,
                    correlation_id=properties.correlation_id,
                    type=properties.type,
                    timestamp=properties.timestamp,
                    app_id=properties.app_id,
                    headers=target.headers,
                    expiration=(
                        str(target.expiration_ms) if target.expiration_ms is not None else None
                    ),
                ),
            )
        channel.basic_ack(delivery_tag)


# --- asyncio side (aio-pika) --------------------------------------------------------------


class AioPikaPublisher:
    """Async counterpart of ``PikaPublisher`` (publisher confirms on a robust connection)."""

    def __init__(self, url: str, *, exchange: str = EXCHANGE) -> None:
        self._url = url
        self._exchange_name = exchange
        self._connection: AbstractRobustConnection | None = None
        self._exchange: AbstractExchange | None = None

    async def _ensure_exchange(self) -> AbstractExchange:
        if self._exchange is None:
            self._connection = await aio_pika.connect_robust(self._url)
            channel = await self._connection.channel(publisher_confirms=True)
            self._exchange = await channel.get_exchange(self._exchange_name, ensure=False)
        return self._exchange

    async def publish(self, envelope: EventEnvelope) -> None:
        exchange = await self._ensure_exchange()
        await exchange.publish(
            aio_pika.Message(
                body=envelope.model_dump_json().encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=str(envelope.event_id),
                correlation_id=str(envelope.correlation_id),
                type=str(envelope.event_type),
                timestamp=envelope.occurred_at,
                app_id=envelope.producer,
            ),
            routing_key=str(envelope.event_type),
        )

    async def close(self) -> None:
        connection, self._connection, self._exchange = self._connection, None, None
        if connection is not None:
            await connection.close()


class AioPikaConsumer:
    """Async counterpart of ``BlockingConsumer``; ``handle`` is usually ``EventRouter.dispatch``."""

    def __init__(
        self,
        url: str,
        service: str,
        handle: Callable[[bytes], Awaitable[object]],
        *,
        policy: RetryPolicy | None = None,
        prefetch: int = 10,
    ) -> None:
        self._url = url
        self.service = service
        self._handle = handle
        self._policy = policy or RetryPolicy()
        self._prefetch = prefetch
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None

    async def start(self) -> None:
        self._connection = await aio_pika.connect_robust(self._url)
        self._channel = await self._connection.channel(publisher_confirms=True)
        await self._channel.set_qos(prefetch_count=self._prefetch)
        queue = await self._channel.get_queue(queue_name(self.service), ensure=False)
        await queue.consume(self.process)
        logger.info("consuming", extra={"queue": queue.name})

    async def process(self, message: AbstractIncomingMessage) -> None:
        try:
            await self._handle(message.body)
        except Exception as error:
            assert self._channel is not None, "process() called before start()"
            target = redirect_failed(self.service, message.headers, error, self._policy)
            log = logger.error if target.queue == dlq_name(self.service) else logger.warning
            log(
                "event handling failed",
                exc_info=True,
                extra={"message_id": message.message_id, "next_queue": target.queue},
            )
            await self._channel.default_exchange.publish(
                aio_pika.Message(
                    body=message.body,
                    content_type=message.content_type,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    message_id=message.message_id,
                    correlation_id=message.correlation_id,
                    type=message.type,
                    timestamp=message.timestamp,
                    app_id=message.app_id,
                    headers=target.headers,
                    expiration=(
                        target.expiration_ms / 1000 if target.expiration_ms is not None else None
                    ),
                ),
                routing_key=target.queue,
            )
        await message.ack()

    async def stop(self) -> None:
        connection, self._connection, self._channel = self._connection, None, None
        if connection is not None:
            await connection.close()


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
        name: str = "event-consumer",
    ) -> None:
        self._consumer = consumer
        self._name = name
        self._probe = probe
        self._retry_seconds = retry_seconds
        self._stop_timeout = stop_timeout
        self._task: asyncio.Task[None] | None = None
        self.started = asyncio.Event()

    def start(self) -> None:
        self._task = asyncio.create_task(self._start_loop(), name=self._name)

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
    """A TCP check of the broker host and port named in an AMQP URL."""
    parts = urlsplit(url)
    return tcp_check(parts.hostname or "localhost", parts.port or 5672)
