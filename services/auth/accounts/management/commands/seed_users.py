"""Demo users: one admin, the demo sellers with approved applications, twenty customers.

Idempotent: ids come from py_common.demo, so a second run only refreshes names and roles.
Seller shops are created by the catalog's own seed from the same demo data.
"""

from typing import Any

from decouple import config
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import ApplicationStatus, Role, SellerApplication, User
from py_common.demo import (
    ADMIN_NAME,
    ADMIN_PHONE,
    CUSTOMER_NAMES,
    CUSTOMER_PHONES,
    SELLERS,
    demo_id,
    demo_user_id,
)


def _upsert_user(phone: str, full_name: str, role: str) -> User:
    user, _ = User.objects.update_or_create(
        id=demo_user_id(phone),
        defaults={"phone": phone, "full_name": full_name, "role": role, "is_active": True},
    )
    return user


class Command(BaseCommand):
    help = "Create demo users (admin, sellers, customers). Safe to run repeatedly."

    def handle(self, *args: Any, **options: Any) -> None:
        with transaction.atomic():
            admin = _upsert_user(ADMIN_PHONE, ADMIN_NAME, Role.ADMIN)
            admin.set_password(config("DEMO_ADMIN_PASSWORD", default="bozorcha-admin"))
            admin.save(update_fields=["password"])

            for seller in SELLERS:
                user = _upsert_user(seller.phone, seller.full_name, Role.SELLER)
                SellerApplication.objects.update_or_create(
                    id=demo_id("seller-application", seller.phone),
                    defaults={
                        "user": user,
                        "shop_name": seller.shop_name,
                        "inn": seller.inn,
                        "description": seller.description,
                        "status": ApplicationStatus.APPROVED,
                        "reviewed_by": admin,
                        "reviewed_at": timezone.now(),
                    },
                )

            for phone, name in zip(CUSTOMER_PHONES, CUSTOMER_NAMES, strict=True):
                _upsert_user(phone, name, Role.CUSTOMER)

        self.stdout.write(
            self.style.SUCCESS(
                f"users ready: 1 admin, {len(SELLERS)} sellers, {len(CUSTOMER_PHONES)} customers"
            )
        )
