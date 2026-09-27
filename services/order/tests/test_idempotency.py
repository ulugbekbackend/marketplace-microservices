"""Checkout is safe to retry: Idempotency-Key per user, stored response, body hash."""

from typing import Any
from uuid import UUID

import fakeredis
import pytest
import redis
from rest_framework.test import APIClient

from orders import idempotency
from orders.models import Order
from tests.conftest import ADDRESS, FakeUpstream, checkout, user_client

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def cart(upstream: FakeUpstream, customer_id: UUID) -> UUID:
    variant_id = upstream.add_variant()
    upstream.put_in_cart(customer_id, variant_id, 1)
    return variant_id


def test_missing_key_is_refused(api: APIClient) -> None:
    for key in (None, "", "   "):
        response = checkout(api, key=key)

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    assert not Order.objects.exists()


def test_overlong_key_is_refused(api: APIClient) -> None:
    response = checkout(api, key="k" * 256)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_INVALID"


def test_same_key_and_body_replays_the_first_response(
    api: APIClient, upstream: FakeUpstream, redis_client: fakeredis.FakeRedis, customer_id: UUID
) -> None:
    first = checkout(api, key="abc")
    second = checkout(api, key="abc")

    assert first.status_code == second.status_code == 202
    assert second.json() == first.json()
    assert second["Idempotent-Replayed"] == "true"
    assert Order.objects.count() == 1
    assert upstream.count("POST", "/reservations/") == 1
    ttl = redis_client.ttl(f"order:idem:{customer_id}:abc")
    assert 0 < ttl <= 24 * 3600
    assert not redis_client.exists(f"order:idem:{customer_id}:abc:lock")


def test_same_key_with_another_body_is_refused(api: APIClient) -> None:
    checkout(api, key="abc")

    response = checkout(api, key="abc", address={**ADDRESS, "street": "Navoiy 5"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert Order.objects.count() == 1


def test_key_still_in_progress_is_refused(
    api: APIClient, redis_client: fakeredis.FakeRedis, customer_id: UUID
) -> None:
    redis_client.set(f"order:idem:{customer_id}:abc:lock", "x")

    response = checkout(api, key="abc")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_IN_PROGRESS"
    assert not Order.objects.exists()


def test_response_stored_by_a_racing_request_is_replayed(
    api: APIClient, redis_client: fakeredis.FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first request finished between our read and our lock."""
    first = checkout(api, key="abc")
    real_get = redis_client.get
    calls = {"n": 0}

    def get(key: str) -> Any:
        calls["n"] += 1
        return None if calls["n"] == 1 else real_get(key)

    monkeypatch.setattr(redis_client, "get", get)

    second = checkout(api, key="abc")

    assert second.json() == first.json()
    assert Order.objects.count() == 1


def test_failures_are_not_stored_so_a_retry_runs_again(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID
) -> None:
    upstream.cart_mode = "down"
    assert checkout(api, key="abc").status_code == 503

    upstream.cart_mode = "ok"
    response = checkout(api, key="abc")

    assert response.status_code == 202
    assert Order.objects.count() == 1


def test_keys_are_scoped_per_user(
    api: APIClient, upstream: FakeUpstream, customer_id: UUID
) -> None:
    other_id = UUID(int=customer_id.int ^ 1)
    upstream.put_in_cart(other_id, upstream.add_variant(), 1)

    checkout(api, key="abc")
    response = checkout(user_client(other_id), key="abc")

    assert response.status_code == 202
    assert Order.objects.count() == 2


def test_redis_down_is_503(api: APIClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class Down:
        def get(self, key: str) -> None:
            raise redis.ConnectionError("down")

    monkeypatch.setattr(idempotency, "get_redis", lambda: Down())

    response = checkout(api, key="abc")

    assert response.status_code == 503
    assert response.json()["error"]["details"] == {"service": "redis"}


def test_request_hash_ignores_key_order() -> None:
    assert idempotency.request_hash({"a": 1, "b": [1, 2]}) == idempotency.request_hash(
        {"b": [1, 2], "a": 1}
    )
    assert idempotency.request_hash({"a": 1}) != idempotency.request_hash({"a": 2})
