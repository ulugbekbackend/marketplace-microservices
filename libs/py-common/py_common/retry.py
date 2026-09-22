"""Redelivery policy for consumers: retry a few times with growing delays, then dead letter."""

from dataclasses import dataclass

from contracts.topology import RETRY_DELAYS_MS

RETRY_COUNT_HEADER = "x-retry-count"


@dataclass(frozen=True, slots=True)
class Retry:
    """Republish to the retry queue and wait this long before the next attempt."""

    delay_ms: int
    attempt: int


@dataclass(frozen=True, slots=True)
class DeadLetter:
    """Attempts are exhausted: park the message in the dead letter queue."""

    attempts: int


Decision = Retry | DeadLetter


class RetryPolicy:
    def __init__(self, delays_ms: tuple[int, ...] = RETRY_DELAYS_MS) -> None:
        if not delays_ms:
            raise ValueError("at least one retry delay is required")
        self._delays = delays_ms

    @property
    def max_attempts(self) -> int:
        return len(self._delays)

    def decide(self, attempt: int) -> Decision:
        """``attempt`` is how many times the message already failed (0 on first failure)."""
        if attempt < 0:
            raise ValueError("attempt must not be negative")
        if attempt >= self.max_attempts:
            return DeadLetter(attempts=attempt)
        return Retry(delay_ms=self._delays[attempt], attempt=attempt + 1)


def attempt_from_headers(headers: dict[str, object] | None) -> int:
    """Read the retry counter a previous delivery left on the message."""
    if not headers:
        return 0
    raw = headers.get(RETRY_COUNT_HEADER, 0)
    if not isinstance(raw, int | str):
        return 0
    try:
        attempt = int(raw)
    except ValueError:
        return 0
    return max(attempt, 0)
