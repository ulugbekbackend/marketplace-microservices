"""HTTP clients: malformed or failing upstream answers become SERVICE_UNAVAILABLE."""

from uuid import UUID, uuid4

import httpx
import pytest

from orders import clients
from orders.clients import ServiceUnavailable
from py_common.context import request_context
from tests.conftest import FakeUpstream


def serve(monkeypatch: pytest.MonkeyPatch, response: httpx.Response) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response

    monkeypatch.setattr(clients, "transport", httpx.MockTransport(handler))
    return seen


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"nope": []}),
        httpx.Response(200, json={"items": [{"variant_id": "not-a-uuid", "qty": 1}]}),
        httpx.Response(404, json={}),
    ],
)
def test_malformed_cart_answer(monkeypatch: pytest.MonkeyPatch, response: httpx.Response) -> None:
    serve(monkeypatch, response)

    with pytest.raises(ServiceUnavailable) as caught:
        clients.get_cart(uuid4())

    assert caught.value.details == {"service": "cart"}
    assert caught.value.status_code == 503


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"items": [{"variant_id": str(uuid4())}]}),
        httpx.Response(200, json={"items": None}),
        httpx.Response(400, json={}),
    ],
)
def test_malformed_bulk_answer(monkeypatch: pytest.MonkeyPatch, response: httpx.Response) -> None:
    serve(monkeypatch, response)

    with pytest.raises(ServiceUnavailable):
        clients.variants_bulk([uuid4()])


def test_cart_clear_failure_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    serve(monkeypatch, httpx.Response(404, json={}))

    with pytest.raises(ServiceUnavailable) as caught:
        clients.clear_cart(uuid4())

    assert caught.value.details == {"service": "cart"}


def test_bulk_is_sent_in_chunks_and_deduplicated(upstream: FakeUpstream) -> None:
    ids = [upstream.add_variant() for _ in range(clients.BULK_CHUNK + 5)]

    found = clients.variants_bulk([*ids, ids[0]])

    assert set(found) == set(ids)
    assert upstream.count("POST", "/variants/bulk/") == 2


def test_correlation_id_is_forwarded(upstream: FakeUpstream) -> None:
    correlation = UUID("01929f7a-0000-7000-8000-000000000001")

    with request_context(correlation_id=correlation):
        clients.get_cart(uuid4())

    assert upstream.requests[-1].headers["X-Correlation-Id"] == str(correlation)


def test_timeout_comes_from_settings(settings: object, upstream: FakeUpstream) -> None:
    settings.INTERNAL_HTTP_TIMEOUT_SECONDS = 1.5  # type: ignore[attr-defined]

    with clients._client("http://cart.test") as client:
        assert client.timeout.read == 1.5
