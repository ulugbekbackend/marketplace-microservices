"""``/internal/auth/users/{id}/contact/``: where the notification service sends messages."""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from accounts.models import User

pytestmark = pytest.mark.django_db


def test_contact_of_a_user(api: APIClient, customer: User) -> None:
    customer.full_name = "Aziz Karimov"
    customer.email = "aziz@example.uz"
    customer.telegram_chat_id = "-1001234"
    customer.save()

    response = api.get(f"/internal/auth/users/{customer.id}/contact/")

    assert response.status_code == 200
    assert response.json() == {
        "phone": customer.phone,
        "full_name": "Aziz Karimov",
        "email": "aziz@example.uz",
        "telegram_chat_id": "-1001234",
    }


def test_a_seller_is_looked_up_by_the_same_id(api: APIClient, seller: User) -> None:
    response = api.get(f"/internal/auth/users/{seller.id}/contact/")

    assert response.status_code == 200
    assert response.json()["phone"] == seller.phone


def test_unknown_or_inactive_user_is_404(api: APIClient, customer: User) -> None:
    customer.is_active = False
    customer.save(update_fields=["is_active"])

    assert api.get(f"/internal/auth/users/{uuid4()}/contact/").status_code == 404
    assert api.get(f"/internal/auth/users/{customer.id}/contact/").status_code == 404


def test_internal_routes_are_not_in_the_public_schema(api: APIClient) -> None:
    schema = api.get("/api/auth/schema/?format=json").json()

    assert all(not path.startswith("/internal") for path in schema["paths"])
