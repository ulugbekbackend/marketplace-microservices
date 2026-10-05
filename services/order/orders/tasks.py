"""Scheduled jobs of the order service (run by the order-worker, see CELERY_BEAT_SCHEDULE)."""

from celery import shared_task

from orders.services import expire_overdue


# Celery ships no type hints, so its decorator is untyped.
@shared_task(name="orders.expire_overdue_orders")  # type: ignore[untyped-decorator]
def expire_overdue_orders() -> int:
    """RESERVED orders past ``reserved_until`` -> EXPIRED, each with ``order.expired``."""
    return expire_overdue()
