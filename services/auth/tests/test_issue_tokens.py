"""``issue_tokens``: token pairs for the e2e and load test drivers, DEBUG only."""

import json
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from pytest_django import Settings

from accounts.models import User
from accounts.tokens import verify_access

pytestmark = pytest.mark.django_db


def issue(*args: str) -> list[dict[str, str]]:
    out = StringIO()
    call_command("issue_tokens", *args, stdout=out)
    issued: list[dict[str, str]] = json.loads(out.getvalue())
    return issued


def test_refuses_without_debug(settings: Settings) -> None:
    settings.DEBUG = False

    with pytest.raises(CommandError, match="DEBUG"):
        issue("--customers", "1")


def test_issues_working_tokens_for_known_and_new_phones(settings: Settings, seller: User) -> None:
    settings.DEBUG = True

    issued = issue("--phone", seller.phone, "--phone", "90 555 12 34")

    assert [row["phone"] for row in issued] == [seller.phone, "+998905551234"]
    assert [row["role"] for row in issued] == ["seller", "customer"]
    identity = verify_access(issued[0]["access"])
    assert (str(identity.user_id), identity.seller_id) == (str(seller.id), seller.id)
    assert User.objects.filter(phone="+998905551234", role="customer").exists()


def test_load_customers_are_created_once(settings: Settings) -> None:
    settings.DEBUG = True

    first = issue("--customers", "3")
    again = issue("--customers", "3")

    assert [row["phone"] for row in first] == ["+998990000000", "+998990000001", "+998990000002"]
    assert [row["user_id"] for row in again] == [row["user_id"] for row in first]
    assert User.objects.filter(phone__startswith="+99899").count() == 3


def test_needs_something_to_issue(settings: Settings) -> None:
    settings.DEBUG = True

    with pytest.raises(CommandError, match="--phone"):
        issue()
