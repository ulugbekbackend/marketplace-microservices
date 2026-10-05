"""Expire every RESERVED order whose reservation time has passed.

The order-worker runs the same function every 30 s (``orders.tasks``); rows another
worker holds are skipped (SKIP LOCKED). ``--order`` ends one reservation right away,
for support and for the system tests, which cannot wait out the reservation window.
"""

from datetime import timedelta
from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError, CommandParser

from orders.models import Order
from orders.services import expire_order, expire_overdue

_ONE_SECOND = timedelta(seconds=1)


class Command(BaseCommand):
    help = "Expire overdue reserved orders (the catalog releases their stock)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument(
            "--order", type=UUID, help="Expire this RESERVED order now, before its deadline."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        order_id: UUID | None = options["order"]
        if order_id is None:
            count = expire_overdue(batch_size=options["batch_size"])
            self.stdout.write(f"expired {count} order(s)")
            return

        order = Order.objects.filter(id=order_id).only("reserved_until").first()
        if order is None:
            raise CommandError(f"order {order_id} not found")
        # Expire as if the deadline had just passed; any other state is left alone.
        moment = order.reserved_until
        if moment is None or not expire_order(order_id, now=moment + _ONE_SECOND):
            raise CommandError(f"order {order_id} is not reserved")
        self.stdout.write(f"expired order {order_id}")
