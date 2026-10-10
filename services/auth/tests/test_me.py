from collections.abc import Callable
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from accounts.models import User

pytestmark = pytest.mark.django_db

URL = "/api/auth/me/"
ClientFor = Callable[[User], APIClient]


def test_get_returns_the_gateway_user(client_for: ClientFor, customer: User) -> None:
    response = client_for(customer).get(URL)

    assert response.status_code == 200
    assert response.json() == {
        "id": str(customer.id),
        "phone": customer.phone,
        "full_name": customer.full_name,
        "email": "",
        "telegram_chat_id": "",
        "role": "customer",
        "date_joined": response.json()["date_joined"],
    }


def test_patch_updates_the_full_name(client_for: ClientFor, customer: User) -> None:
    response = client_for(customer).patch(URL, {"full_name": "  Aziz Karimov "}, format="json")

    assert response.status_code == 200
    assert response.json()["full_name"] == "Aziz Karimov"
    customer.refresh_from_db()
    assert customer.full_name == "Aziz Karimov"


def test_patch_sets_the_notification_channels(client_for: ClientFor, customer: User) -> None:
    response = client_for(customer).patch(
        URL, {"email": " Aziz@Example.UZ ", "telegram_chat_id": "123456789"}, format="json"
    )

    assert response.status_code == 200
    assert response.json()["email"] == "aziz@example.uz"
    assert response.json()["telegram_chat_id"] == "123456789"
    customer.refresh_from_db()
    assert (customer.email, customer.telegram_chat_id) == ("aziz@example.uz", "123456789")


def test_patch_clears_a_channel_with_an_empty_value(client_for: ClientFor, customer: User) -> None:
    customer.email = "old@example.uz"
    customer.save(update_fields=["email"])

    response = client_for(customer).patch(URL, {"email": ""}, format="json")

    assert response.status_code == 200
    customer.refresh_from_db()
    assert customer.email == ""


@pytest.mark.parametrize(
    "body",
    [{"email": "not-an-email"}, {"telegram_chat_id": "abc"}, {"telegram_chat_id": "1" * 21}],
)
def test_patch_rejects_invalid_channels(
    client_for: ClientFor, customer: User, body: dict[str, str]
) -> None:
    response = client_for(customer).patch(URL, body, format="json")

    assert response.status_code == 400
    assert set(response.json()["error"]["details"]) == set(body)


def test_patch_cannot_change_role_or_phone(client_for: ClientFor, customer: User) -> None:
    client_for(customer).patch(
        URL, {"full_name": "X", "role": "admin", "phone": "+998911111111"}, format="json"
    )

    customer.refresh_from_db()
    assert customer.role == "customer"
    assert customer.phone != "+998911111111"


def test_patch_rejects_a_blank_name(client_for: ClientFor, customer: User) -> None:
    response = client_for(customer).patch(URL, {"full_name": "   "}, format="json")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_anonymous_is_401(api: APIClient) -> None:
    assert api.get(URL).status_code == 401
    assert api.patch(URL, {"full_name": "x"}, format="json").status_code == 401


def test_malformed_gateway_headers_are_401(api: APIClient) -> None:
    response = api.get(URL, HTTP_X_USER_ID="nope", HTTP_X_USER_ROLE="customer")

    assert response.status_code == 401


def test_unknown_user_is_404(api: APIClient) -> None:
    response = api.get(URL, HTTP_X_USER_ID=str(uuid4()), HTTP_X_USER_ROLE="customer")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "USER_NOT_FOUND"
