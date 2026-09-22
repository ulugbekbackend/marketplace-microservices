"""Gateway headers, structured logs and request context."""

import json
import logging
from uuid import uuid4

import pytest

from contracts.enums import UserRole
from py_common.auth import AuthError, parse_user_headers
from py_common.context import get_correlation_id, request_context
from py_common.logging import configure_logging


def test_anonymous_request_has_no_user() -> None:
    assert parse_user_headers({}) is None
    assert parse_user_headers({"X-Request-Id": "abc"}) is None


def test_headers_are_case_insensitive() -> None:
    user_id = uuid4()
    user = parse_user_headers({"x-user-id": str(user_id), "X-USER-ROLE": "customer"})
    assert user is not None
    assert user.user_id == user_id
    assert user.role is UserRole.CUSTOMER
    assert user.seller_id is None


def test_seller_headers() -> None:
    seller_id = uuid4()
    user = parse_user_headers(
        {"X-User-Id": str(uuid4()), "X-User-Role": "seller", "X-Seller-Id": str(seller_id)}
    )
    assert user is not None
    assert user.is_seller
    assert user.seller_id == seller_id


@pytest.mark.parametrize(
    "headers",
    [
        {"X-User-Id": str(uuid4())},
        {"X-User-Role": "customer"},
        {"X-User-Id": "not-a-uuid", "X-User-Role": "customer"},
        {"X-User-Id": str(uuid4()), "X-User-Role": "root"},
        {"X-User-Id": str(uuid4()), "X-User-Role": "seller", "X-Seller-Id": "nope"},
    ],
)
def test_malformed_headers_raise(headers: dict[str, str]) -> None:
    with pytest.raises(AuthError):
        parse_user_headers(headers)


def test_admin_flag() -> None:
    user = parse_user_headers({"X-User-Id": str(uuid4()), "X-User-Role": "admin"})
    assert user is not None
    assert user.is_admin and not user.is_seller


def test_log_line_is_json_with_correlation_id(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("catalog")
    correlation_id = uuid4()
    with request_context(correlation_id=correlation_id):
        logging.getLogger("test").info("stock reserved", extra={"order_id": "42"})

    record = json.loads(capsys.readouterr().out.strip())
    assert record["service"] == "catalog"
    assert record["level"] == "INFO"
    assert record["message"] == "stock reserved"
    assert record["correlation_id"] == str(correlation_id)
    assert record["order_id"] == "42"
    assert record["timestamp"].endswith("+00:00")


def test_exception_is_logged(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("order")
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("test").exception("failed")

    record = json.loads(capsys.readouterr().out.strip())
    assert "ValueError: boom" in record["exception"]


def test_context_is_restored_after_exit() -> None:
    assert get_correlation_id() is None
    with request_context() as (correlation_id, request_id):
        assert get_correlation_id() == correlation_id
        assert request_id == str(correlation_id)
    assert get_correlation_id() is None
