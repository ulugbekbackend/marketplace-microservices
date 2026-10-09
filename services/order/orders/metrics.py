"""Checkout metrics. ``checkout_failed_total`` counts both refusals at checkout time
(empty cart, unavailable items, catalog down) and orders cancelled because the stock could
not be reserved (the order consumer exposes those on its own port)."""

from prometheus_client import Counter

CHECKOUT_TOTAL = Counter("checkout_total", "Checkout attempts that reached the order service")
CHECKOUT_FAILED = Counter(
    "checkout_failed_total", "Checkouts that did not end in a reservation", ["reason"]
)
