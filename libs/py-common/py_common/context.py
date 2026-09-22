"""Request scoped context shared by logging, outgoing calls and published events."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from uuid import UUID

from contracts.ids import uuid7

_correlation_id: ContextVar[UUID | None] = ContextVar("correlation_id", default=None)
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_correlation_id() -> UUID | None:
    return _correlation_id.get()


def get_request_id() -> str | None:
    return _request_id.get()


def set_correlation_id(value: UUID | None) -> Token[UUID | None]:
    return _correlation_id.set(value)


def set_request_id(value: str | None) -> Token[str | None]:
    return _request_id.set(value)


@contextmanager
def request_context(
    *, correlation_id: UUID | None = None, request_id: str | None = None
) -> Iterator[tuple[UUID, str]]:
    """Bind a correlation id and request id for the duration of a request or message."""
    correlation = correlation_id or uuid7()
    request = request_id or str(correlation)
    correlation_token = _correlation_id.set(correlation)
    request_token = _request_id.set(request)
    try:
        yield correlation, request
    finally:
        _correlation_id.reset(correlation_token)
        _request_id.reset(request_token)
