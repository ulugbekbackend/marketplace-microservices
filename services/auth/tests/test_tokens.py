import threading
from datetime import timedelta

import jwt
import pytest
from django.db import connection
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from accounts import tokens
from accounts.models import Role, User
from tests.conftest import KeyPair
from tests.factories import make_user

pytestmark = pytest.mark.django_db

REFRESH = "/api/auth/token/refresh/"
LOGOUT = "/api/auth/logout/"


def claims(token: str, keys: KeyPair) -> dict[str, object]:
    return jwt.decode(token, keys.public_pem, algorithms=["RS256"], issuer="marketplace-auth")


def test_customer_tokens_carry_subject_role_and_expiry(customer: User, jwt_keys: KeyPair) -> None:
    pair = tokens.issue_tokens(customer)

    access = claims(pair.access, jwt_keys)
    refresh = claims(pair.refresh, jwt_keys)
    assert access["sub"] == refresh["sub"] == str(customer.id)
    assert access["role"] == Role.CUSTOMER
    assert "seller_id" not in access
    assert access["token_type"] == "access"
    assert refresh["token_type"] == "refresh"
    assert int(access["exp"]) - int(access["iat"]) == 15 * 60  # type: ignore[call-overload]
    assert int(refresh["exp"]) - int(refresh["iat"]) == 30 * 24 * 3600  # type: ignore[call-overload]
    header = jwt.get_unverified_header(pair.access)
    assert header["alg"] == "RS256"
    assert header["kid"] == tokens.jwks()["keys"][0]["kid"]


def test_seller_tokens_carry_seller_id_equal_to_user_id(seller: User, jwt_keys: KeyPair) -> None:
    access = claims(tokens.issue_tokens(seller).access, jwt_keys)

    assert access["role"] == Role.SELLER
    assert access["seller_id"] == str(seller.id)


def test_issued_refresh_is_tracked(customer: User) -> None:
    pair = tokens.issue_tokens(customer)

    outstanding = OutstandingToken.objects.get(user=customer)
    assert outstanding.token == pair.refresh


def test_refresh_rotates_and_blacklists_the_old_token(api: APIClient, customer: User) -> None:
    old = tokens.issue_tokens(customer)

    response = api.post(REFRESH, {"refresh": old.refresh}, format="json")

    assert response.status_code == 200
    new = response.json()
    assert new["refresh"] != old.refresh
    assert new["access"] != old.access
    assert BlacklistedToken.objects.filter(token__token=old.refresh).exists()

    reuse = api.post(REFRESH, {"refresh": old.refresh}, format="json")
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "TOKEN_INVALID"

    assert api.post(REFRESH, {"refresh": new["refresh"]}, format="json").status_code == 200


def test_refresh_picks_up_a_role_change(api: APIClient, customer: User, jwt_keys: KeyPair) -> None:
    old = tokens.issue_tokens(customer)
    User.objects.filter(pk=customer.pk).update(role=Role.SELLER)

    response = api.post(REFRESH, {"refresh": old.refresh}, format="json")

    access = claims(response.json()["access"], jwt_keys)
    assert access["role"] == Role.SELLER
    assert access["seller_id"] == str(customer.id)


@pytest.mark.parametrize("token", ["garbage", "a.b.c", ""])
def test_refresh_rejects_malformed_tokens(api: APIClient, token: str) -> None:
    response = api.post(REFRESH, {"refresh": token}, format="json")

    assert response.status_code in (400, 401)
    assert response.json()["error"]["code"] in ("TOKEN_INVALID", "VALIDATION_ERROR")


def test_refresh_rejects_an_access_token(api: APIClient, customer: User) -> None:
    pair = tokens.issue_tokens(customer)

    response = api.post(REFRESH, {"refresh": pair.access}, format="json")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_INVALID"


def test_refresh_rejects_a_foreign_signature(
    api: APIClient, customer: User, foreign_keys: KeyPair
) -> None:
    pair = tokens.issue_tokens(customer)
    payload = jwt.decode(pair.refresh, options={"verify_signature": False})
    forged = jwt.encode(payload, foreign_keys.private_pem, algorithm="RS256")

    assert api.post(REFRESH, {"refresh": forged}, format="json").status_code == 401


def test_refresh_rejects_an_expired_token(api: APIClient, customer: User) -> None:
    pair = tokens.issue_tokens(customer)
    token = tokens.ServiceRefreshToken(pair.refresh)  # type: ignore[arg-type]
    token.set_exp(from_time=token.current_time - timedelta(days=31))

    assert api.post(REFRESH, {"refresh": str(token)}, format="json").status_code == 401


def test_refresh_rejects_an_untracked_token(api: APIClient, customer: User) -> None:
    pair = tokens.issue_tokens(customer)
    OutstandingToken.objects.all().delete()

    assert api.post(REFRESH, {"refresh": pair.refresh}, format="json").status_code == 401


def test_refresh_rejects_an_inactive_user(api: APIClient) -> None:
    user = make_user()
    pair = tokens.issue_tokens(user)
    User.objects.filter(pk=user.pk).update(is_active=False)

    response = api.post(REFRESH, {"refresh": pair.refresh}, format="json")

    assert response.status_code == 401
    assert not BlacklistedToken.objects.exists()  # nothing was spent


def test_logout_blacklists_the_refresh_token(api: APIClient, customer: User) -> None:
    pair = tokens.issue_tokens(customer)

    response = api.post(LOGOUT, {"refresh": pair.refresh}, format="json")

    assert response.status_code == 204
    assert BlacklistedToken.objects.filter(token__token=pair.refresh).exists()
    assert api.post(REFRESH, {"refresh": pair.refresh}, format="json").status_code == 401


def test_logout_is_idempotent(api: APIClient, customer: User) -> None:
    pair = tokens.issue_tokens(customer)
    api.post(LOGOUT, {"refresh": pair.refresh}, format="json")

    assert api.post(LOGOUT, {"refresh": pair.refresh}, format="json").status_code == 204
    assert BlacklistedToken.objects.count() == 1


def test_logout_rejects_garbage_access_and_unknown_tokens(api: APIClient, customer: User) -> None:
    pair = tokens.issue_tokens(customer)

    assert api.post(LOGOUT, {"refresh": "garbage"}, format="json").status_code == 401
    assert api.post(LOGOUT, {"refresh": pair.access}, format="json").status_code == 401
    OutstandingToken.objects.all().delete()
    assert api.post(LOGOUT, {"refresh": pair.refresh}, format="json").status_code == 401


def test_logout_requires_a_body(api: APIClient) -> None:
    response = api.post(LOGOUT, {}, format="json")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db(transaction=True)
def test_concurrent_refresh_with_one_token_succeeds_once() -> None:
    """Two requests racing with the same refresh token: the row lock lets only one through."""
    user = make_user()
    pair = tokens.issue_tokens(user)
    barrier = threading.Barrier(4)
    results: list[str] = []

    def use() -> None:
        try:
            barrier.wait()
            tokens.rotate_refresh(pair.refresh)
            results.append("ok")
        except tokens.InvalidTokenError:
            results.append("rejected")
        finally:
            connection.close()

    threads = [threading.Thread(target=use) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == ["ok", "rejected", "rejected", "rejected"]
    assert OutstandingToken.objects.filter(user=user).count() == 2
