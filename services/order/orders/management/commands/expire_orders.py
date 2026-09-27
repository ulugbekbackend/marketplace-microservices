"""Expire every RESERVED order whose reservation time has passed.

P4 runs this on a schedule; rows another worker holds are skipped (SKIP LOCKED).
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from orders.services import expire_overdue


class Command(BaseCommand):
    help = "Expire overdue reserved orders and release their stock."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args: Any, **options: Any) -> None:
        count = expire_overdue(batch_size=options["batch_size"])
        self.stdout.write(f"expired {count} order(s)")
