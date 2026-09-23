"""The demo user seed creates the expected people and is safe to run twice."""

import pytest
from django.core.management import call_command

from accounts.models import ApplicationStatus, Role, SellerApplication, User
from py_common.demo import ADMIN_PHONE, CUSTOMER_PHONES, SELLERS, demo_user_id

pytestmark = pytest.mark.django_db


def test_seed_creates_demo_users() -> None:
    call_command("seed_users")

    admin = User.objects.get(phone=ADMIN_PHONE)
    assert admin.role == Role.ADMIN
    assert admin.has_usable_password()

    sellers = User.objects.filter(role=Role.SELLER)
    assert sellers.count() == len(SELLERS)
    assert {seller.id for seller in sellers} == {seller.user_id for seller in SELLERS}

    assert User.objects.filter(role=Role.CUSTOMER).count() == len(CUSTOMER_PHONES)
    assert SellerApplication.objects.filter(status=ApplicationStatus.APPROVED).count() == len(
        SELLERS
    )


def test_seed_is_idempotent() -> None:
    call_command("seed_users")
    call_command("seed_users")

    assert User.objects.count() == 1 + len(SELLERS) + len(CUSTOMER_PHONES)
    assert SellerApplication.objects.count() == len(SELLERS)


def test_seed_ids_match_the_shared_demo_ids() -> None:
    call_command("seed_users")

    seller = SELLERS[0]
    assert User.objects.get(phone=seller.phone).id == demo_user_id(seller.phone)
