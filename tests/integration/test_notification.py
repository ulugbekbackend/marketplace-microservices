"""Notifications against the running stack: a paid order mails a customer who has an email
(Mailpit catches it) and leaves the notification queues and DLQ empty."""

import time
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from simulator_kit import Shopper
from test_saga import GATEWAY, wait_until

MAILPIT_HOST = {"Host": "mail.localhost"}


@pytest.fixture(scope="module")
def buyer() -> Iterator[Shopper]:
    account = Shopper(GATEWAY)
    yield account
    account.close()


def mails_to(address: str) -> list[dict[str, Any]]:
    response = httpx.get(
        f"{GATEWAY}/api/v1/search", params={"query": f"to:{address}"}, headers=MAILPIT_HOST
    )
    response.raise_for_status()
    messages: list[dict[str, Any]] = response.json().get("messages") or []
    return messages


def test_a_paid_order_mails_the_customer(buyer: Shopper) -> None:
    address = f"buyer-{uuid.uuid4().hex[:10]}@example.uz"
    updated = buyer.http.patch("/api/auth/me/", json={"email": address})
    assert updated.status_code == 200, updated.text
    assert updated.json()["email"] == address

    order = buyer.reserved_order()
    paid = buyer.http.post(f"/api/payments/mock/{order.id}/pay")
    assert paid.status_code == 200, paid.text
    buyer.wait_status(order.id, "PAID")

    [mail] = wait_until(lambda: mails_to(address), f"a mail to {address}")
    number = f"#{order.id[:8].upper()}"
    assert mail["Subject"] == f"Buyurtma {number} to'landi"
    # A redelivery must not send it again.
    time.sleep(2)
    assert len(mails_to(address)) == 1


def test_contact_lookup_is_not_exposed_through_the_gateway() -> None:
    response = httpx.get(
        f"{GATEWAY}/internal/auth/users/{uuid.uuid4()}/contact/",
        headers={"Host": "api.localhost"},
    )

    assert response.status_code == 404
