"""RabbitMQ topology: one topic exchange, one queue per consuming service, retry and DLQ."""

from typing import Any

from contracts.enums import EventType

EXCHANGE = "marketplace.events"
RETRY_EXCHANGE = "marketplace.retry"

#: Which events each service consumes. Producers may publish anything on the exchange.
CONSUMER_BINDINGS: dict[str, tuple[EventType, ...]] = {
    "catalog": (
        EventType.ORDER_CREATED,
        EventType.ORDER_PAID,
        EventType.ORDER_EXPIRED,
        EventType.ORDER_CANCELLED,
        EventType.SELLER_APPROVED,
    ),
    "order": (
        EventType.STOCK_RESERVED,
        EventType.STOCK_FAILED,
        EventType.PAYMENT_PAID,
        EventType.PAYMENT_REFUNDED,
    ),
    "payment": (
        EventType.ORDER_REFUND_REQUESTED,
        EventType.ORDER_PAID,
        EventType.SUB_ORDER_STATUS_CHANGED,
    ),
    "search": (
        EventType.PRODUCT_UPDATED,
        EventType.PRODUCT_DELETED,
    ),
    "notification": (
        EventType.ORDER_PAID,
        EventType.ORDER_EXPIRED,
        EventType.ORDER_CANCELLED,
        EventType.PAYMENT_REFUNDED,
        EventType.SUB_ORDER_STATUS_CHANGED,
        EventType.SELLER_APPROVED,
    ),
}

#: Delay before each redelivery attempt, in milliseconds.
RETRY_DELAYS_MS = (1_000, 5_000, 25_000)

_QUEUE_ARGS: dict[str, Any] = {"x-queue-type": "quorum"}


def queue_name(service: str) -> str:
    return f"{service}.q"


def retry_queue_name(service: str) -> str:
    return f"{service}.q.retry"


def dlq_name(service: str) -> str:
    return f"{service}.q.dlq"


def _queue(name: str, vhost: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "vhost": vhost,
        "durable": True,
        "auto_delete": False,
        "arguments": arguments,
    }


def _binding(source: str, destination: str, routing_key: str, vhost: str) -> dict[str, Any]:
    return {
        "source": source,
        "vhost": vhost,
        "destination": destination,
        "destination_type": "queue",
        "routing_key": routing_key,
        "arguments": {},
    }


def render_definitions(vhost: str = "/") -> dict[str, Any]:
    """Build the RabbitMQ definitions document (exchanges, queues, bindings).

    Users are intentionally absent: definitions are imported over the management API
    after boot, so credentials stay in the environment and never in a committed file.
    """
    exchanges = [
        {
            "name": name,
            "vhost": vhost,
            "type": "topic",
            "durable": True,
            "auto_delete": False,
            "internal": False,
            "arguments": {},
        }
        for name in (EXCHANGE, RETRY_EXCHANGE)
    ]
    queues: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []

    for service, events in CONSUMER_BINDINGS.items():
        main, retry, dead = queue_name(service), retry_queue_name(service), dlq_name(service)
        queues.append(_queue(main, vhost, dict(_QUEUE_ARGS)))
        queues.append(
            _queue(
                retry,
                vhost,
                {
                    **_QUEUE_ARGS,
                    # An expired retry message is dead lettered straight back to the main queue.
                    "x-dead-letter-exchange": RETRY_EXCHANGE,
                    "x-dead-letter-routing-key": main,
                },
            )
        )
        queues.append(_queue(dead, vhost, dict(_QUEUE_ARGS)))

        bindings += [_binding(EXCHANGE, main, str(event), vhost) for event in events]
        bindings.append(_binding(RETRY_EXCHANGE, main, main, vhost))
        bindings.append(_binding(RETRY_EXCHANGE, dead, dead, vhost))

    return {
        "vhosts": [{"name": vhost}],
        "permissions": [],
        "policies": [],
        "parameters": [],
        "exchanges": exchanges,
        "queues": queues,
        "bindings": bindings,
    }
