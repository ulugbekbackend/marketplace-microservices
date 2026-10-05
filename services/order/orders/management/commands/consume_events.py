"""Consume order.q until SIGTERM / SIGINT (compose service order-consumer).

Failed messages go to the retry queue and, after the last attempt or on a permanent error
(unknown order, malformed payload), to the dead letter queue.
"""

from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from orders.saga import HANDLERS
from py_common.rabbit import BlockingConsumer, make_dispatch, stop_on_signals


def make_handler() -> Callable[[bytes], None]:
    dispatch = make_dispatch(HANDLERS)

    def handle(body: bytes) -> None:
        # A long-lived process: drop a connection the database closed meanwhile.
        close_old_connections()
        dispatch(body)

    return handle


class Command(BaseCommand):
    help = "Consume the events of the order service until stopped."

    def handle(self, *args: Any, **options: Any) -> None:
        consumer = BlockingConsumer(settings.RABBITMQ_URL, settings.SERVICE_NAME, make_handler())
        consumer.run(stop_on_signals())
