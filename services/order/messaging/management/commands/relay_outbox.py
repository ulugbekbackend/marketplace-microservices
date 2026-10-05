"""Publish outbox rows to RabbitMQ until SIGTERM / SIGINT (compose service order-relay)."""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser
from django.db import close_old_connections, transaction

from messaging.outbox import DjangoOutboxStore
from py_common.outbox import Publisher, publish_pending
from py_common.rabbit import PikaPublisher, run_relay, stop_on_signals


def publish_batch(publisher: Publisher, *, limit: int) -> int:
    """One batch in one transaction: the row locks hold until the rows are stamped."""
    close_old_connections()
    with transaction.atomic():
        return publish_pending(DjangoOutboxStore(), publisher, limit=limit)


class Command(BaseCommand):
    help = "Publish pending outbox events to RabbitMQ until stopped."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--batch-size", type=int, default=settings.OUTBOX_RELAY_BATCH_SIZE)
        parser.add_argument(
            "--interval", type=float, default=settings.OUTBOX_RELAY_INTERVAL_SECONDS
        )

    def handle(self, *args: Any, **options: Any) -> None:
        limit: int = options["batch_size"]
        publisher = PikaPublisher(settings.RABBITMQ_URL)
        try:
            run_relay(
                lambda: publish_batch(publisher, limit=limit),
                stop_on_signals(),
                interval=options["interval"],
                idle=publisher.idle,
            )
        finally:
            publisher.close()
