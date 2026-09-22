"""The ForwardAuth endpoint Traefik calls before every protected request."""

from datetime import timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pytest_django import DjangoAssertNumQueries
from rest_framework.test import APIClient

from accounts import tokens
from accounts.models import Role, User
from tests.conftest import KeyPair

pytestmark = pytest.mark.django_db

URL = "/api/auth/verify/"


def bearer(token: str) -> str:
    return f"Bearer {token}"


def test_customer_token_yields_identity_headers(api: APIClient, customer: User) -> None:
    response = api.get(URL, HTTP_AUTHORIZATION=bearer(tokens.issue_tokens(customer).access))

    assert response.status_code == 200
    assert response["X-User-Id"] == str(customer.id)
    assert response["X-User-Role"] == Role.CUSTOMER
    assert "X-Seller-Id" not in response


def test_seller_token_also_yields_seller_id(api: APIClient, seller: User) -> None:
    response = api.get(URL, HTTP_AUTHORIZATION=bearer(tokens.issue_tokens(seller).access))

    assert response.status_code == 200
    assert response["X-User-Role"] == Role.SELLER
    assert response["X-Seller-Id"] == str(seller.id)


def test_optional_mode_with_a_valid_token_still_identifies(api: APIClient, customer: User) -> None:
    access = tokens.issue_tokens(customer).access

    response = api.get(f"{URL}?optional=1", HTTP_AUTHORIZATION=bearer(access))

    assert response.status_code == 200
    assert response["X-User-Id"] == str(customer.id)


def test_missing_token_is_401(api: APIClient) -> None:
    response = api.get(URL)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


def test_missing_token_in_optional_mode_passes_as_guest(api: APIClient) -> None:
    response = api.get(f"{URL}?optional=1")

    assert response.status_code == 200
    assert "X-User-Id" not in response
    assert "X-User-Role" not in response
    assert "X-Seller-Id" not in response


def expired_access(user: User) -> str:
    token = tokens.ServiceAccessToken()
    token["sub"] = str(user.id)
    token["role"] = user.role
    token.set_exp(from_time=token.current_time - timedelta(hours=1))
    return str(token)


def foreign_access(user: User, keys: KeyPair) -> str:
    payload = jwt.decode(tokens.issue_tokens(user).access, options={"verify_signature": False})
    return jwt.encode(payload, keys.private_pem, algorithm="RS256")


@pytest.mark.parametrize("optional", ["", "?optional=1"])
@pytest.mark.parametrize("kind", ["expired", "garbage", "foreign", "refresh", "scheme", "empty"])
def test_bad_tokens_are_401_in_both_modes(
    api: APIClient, customer: User, foreign_keys: KeyPair, kind: str, optional: str
) -> None:
    header = {
        "expired": f"Bearer {expired_access(customer)}",
        "garbage": "Bearer not-a-jwt",
        "foreign": f"Bearer {foreign_access(customer, foreign_keys)}",
        "refresh": f"Bearer {tokens.issue_tokens(customer).refresh}",
        "scheme": f"Basic {tokens.issue_tokens(customer).access}",
        "empty": "Bearer ",
    }[kind]

    response = api.get(f"{URL}{optional}", HTTP_AUTHORIZATION=header)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_INVALID"
    assert "X-User-Id" not in response


def test_token_without_valid_subject_is_401(api: APIClient) -> None:
    token = tokens.ServiceAccessToken()
    token["sub"] = "not-a-uuid"

    assert api.get(URL, HTTP_AUTHORIZATION=bearer(str(token))).status_code == 401


def test_inactive_user_is_401(api: APIClient, customer: User) -> None:
    access = tokens.issue_tokens(customer).access
    User.objects.filter(pk=customer.pk).update(is_active=False)

    assert api.get(URL, HTTP_AUTHORIZATION=bearer(access)).status_code == 401


def test_deleted_user_is_401(api: APIClient, customer: User) -> None:
    access = tokens.issue_tokens(customer).access
    User.objects.filter(pk=customer.pk).delete()

    assert api.get(URL, HTTP_AUTHORIZATION=bearer(access)).status_code == 401


def test_role_comes_from_the_database(api: APIClient, customer: User) -> None:
    access = tokens.issue_tokens(customer).access
    User.objects.filter(pk=customer.pk).update(role=Role.SELLER)

    response = api.get(URL, HTTP_AUTHORIZATION=bearer(access))

    assert response["X-User-Role"] == Role.SELLER
    assert response["X-Seller-Id"] == str(customer.id)


def test_verify_ignores_identity_headers_sent_by_the_client(api: APIClient, customer: User) -> None:
    response = api.get(URL, HTTP_X_USER_ID=str(customer.id), HTTP_X_USER_ROLE="admin")

    assert response.status_code == 401


def test_verify_uses_at_most_one_query(
    api: APIClient, customer: User, django_assert_max_num_queries: DjangoAssertNumQueries
) -> None:
    access = tokens.issue_tokens(customer).access

    with django_assert_max_num_queries(1):
        assert api.get(URL, HTTP_AUTHORIZATION=bearer(access)).status_code == 200


def test_jwks_publishes_the_public_key(api: APIClient, customer: User) -> None:
    response = api.get("/api/auth/.well-known/jwks.json")

    assert response.status_code == 200
    assert "max-age" in response["Cache-Control"]
    keys = response.json()["keys"]
    assert len(keys) == 1
    jwk = keys[0]
    assert jwk["kty"] == "RSA" and jwk["alg"] == "RS256" and jwk["use"] == "sig"

    access = tokens.issue_tokens(customer).access
    assert jwt.get_unverified_header(access)["kid"] == jwk["kid"]
    public_key = jwt.PyJWK(jwk).key
    decoded = jwt.decode(access, public_key, algorithms=["RS256"], issuer="marketplace-auth")
    assert decoded["sub"] == str(customer.id)


def test_jwks_matches_the_configured_key_file(jwt_keys: KeyPair) -> None:
    loaded = load_pem_public_key(jwt_keys.public_pem.encode())
    assert isinstance(loaded, RSAPublicKey)
    expected = loaded.public_numbers()
    jwk = tokens.jwks()["keys"][0]
    actual = jwt.PyJWK(jwk).key.public_numbers()

    assert (actual.n, actual.e) == (expected.n, expected.e)
