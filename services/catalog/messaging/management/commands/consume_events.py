"""Consume ``catalog.q`` until SIGTERM / SIGINT (compose service catalog-consumer)."""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from messaging.handlers import HANDLERS
from py_common.rabbit import BlockingConsumer, make_dispatch, stop_on_signals

SERVICE = "catalog"

_dispatch = make_dispatch(HANDLERS)


def handle_message(body: bytes) -> None:
    # A long running process: drop a connection the database closed meanwhile.
    close_old_connections()
    _dispatch(body)


class Command(BaseCommand):
    help = "Handle order and seller events from RabbitMQ until stopped."

    def handle(self, *args: Any, **options: Any) -> None:
        BlockingConsumer(settings.RABBITMQ_URL, SERVICE, handle_message).run(stop_on_signals())
