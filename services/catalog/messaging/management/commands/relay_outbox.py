"""Publish outbox rows to RabbitMQ until SIGTERM / SIGINT (compose service catalog-relay)."""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser
from django.db import close_old_connections

from messaging.outbox import relay_batch
from py_common.rabbit import PikaPublisher, run_relay, stop_on_signals


class Command(BaseCommand):
    help = "Publish pending outbox events to RabbitMQ until stopped."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument(
            "--interval", type=float, default=1.0, help="Seconds to wait after an empty batch."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        limit: int = options["batch_size"]
        publisher = PikaPublisher(settings.RABBITMQ_URL)

        def batch() -> int:
            # A long running process: drop a connection the database closed meanwhile.
            close_old_connections()
            return relay_batch(publisher, limit=limit)

        try:
            run_relay(batch, stop_on_signals(), interval=options["interval"])
        finally:
            publisher.close()
