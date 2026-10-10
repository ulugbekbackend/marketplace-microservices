"""Provider callback metrics: every error answer given to Payme or Click, by its code."""

from prometheus_client import Counter

PAYMENT_ERRORS = Counter(
    "payment_errors_total", "Provider callbacks answered with an error", ["provider", "code"]
)
