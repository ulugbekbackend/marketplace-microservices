"""Model factories. Tests call the typed ``make_*`` helpers."""

from typing import Any

from factory.declarations import Sequence, SubFactory
from factory.django import DjangoModelFactory
from factory.faker import Faker

from accounts.models import ApplicationStatus, Role, SellerApplication, User


class UserFactory(DjangoModelFactory[User]):
    class Meta:
        model = User

    phone = Sequence(lambda n: f"+99890{1000000 + n:07d}")  # type: ignore[no-untyped-call]
    full_name = Faker("name")  # type: ignore[no-untyped-call]
    role = Role.CUSTOMER
    password = "!unusable"


class SellerApplicationFactory(DjangoModelFactory[SellerApplication]):
    class Meta:
        model = SellerApplication

    user = SubFactory(UserFactory)  # type: ignore[no-untyped-call]
    shop_name = Sequence(lambda n: f"Shop {n}")  # type: ignore[no-untyped-call]
    inn = "123456789"
    description = "Handmade goods"
    status = ApplicationStatus.PENDING


def make_user(**fields: Any) -> User:
    return UserFactory.create(**fields)


def make_application(**fields: Any) -> SellerApplication:
    return SellerApplicationFactory.create(**fields)
