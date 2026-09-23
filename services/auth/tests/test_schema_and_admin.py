"""OpenAPI completeness, Django admin access and the user manager."""

from pathlib import Path
from uuid import uuid4

import pytest
import redis
import yaml
from django.core.management import call_command
from django.test import Client
from django.utils import timezone
from pytest_django import Settings

from accounts import redis_client
from accounts.models import OtpCode, Outbox, Role, User
from tests.factories import make_application, make_user

EXPECTED = {
    "/api/auth/otp/send/": {"post"},
    "/api/auth/otp/verify/": {"post"},
    "/api/auth/token/refresh/": {"post"},
    "/api/auth/logout/": {"post"},
    "/api/auth/me/": {"get", "patch"},
    "/api/auth/seller/apply/": {"post"},
    "/api/auth/seller/application/": {"get"},
    "/api/auth/verify/": {"get"},
    "/api/auth/.well-known/jwks.json": {"get"},
    "/api/auth/admin/seller-applications/": {"get"},
    "/api/auth/admin/seller-applications/{application_id}/approve/": {"post"},
    "/api/auth/admin/seller-applications/{application_id}/reject/": {"post"},
}


def test_schema_documents_every_endpoint_without_warnings(tmp_path: Path) -> None:
    target = tmp_path / "schema.yaml"

    call_command("spectacular", "--fail-on-warn", "--file", str(target))

    schema = yaml.safe_load(target.read_text(encoding="utf-8"))
    for path, methods in EXPECTED.items():
        assert path in schema["paths"], path
        assert methods <= set(schema["paths"][path]), path
    login = schema["paths"]["/api/auth/otp/verify/"]["post"]
    assert "200" in login["responses"] and "400" in login["responses"]
    assert "gatewayBearer" in schema["components"]["securitySchemes"]


def test_schema_endpoint_is_served(client: Client) -> None:
    assert client.get("/api/auth/schema/").status_code == 200


@pytest.mark.django_db
def test_createsuperuser_makes_an_admin_with_a_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "s3cret-pass-for-tests")

    call_command("createsuperuser", "--noinput", "--phone", "+998971112233")

    admin = User.objects.get(phone="+998971112233")
    assert admin.role == Role.ADMIN
    assert admin.check_password("s3cret-pass-for-tests")
    assert admin.is_staff and admin.is_superuser
    assert admin.has_perm("accounts.view_user") and admin.has_module_perms("accounts")


@pytest.mark.django_db
def test_create_superuser_requires_a_password() -> None:
    with pytest.raises(ValueError, match="password"):
        User.objects.create_superuser("+998971112233")


@pytest.mark.django_db
def test_create_user_normalises_the_phone_and_has_no_password() -> None:
    user = User.objects.create_user("90 765 43 21")

    assert user.phone == "+998907654321"
    assert not user.has_usable_password()
    assert not user.is_staff
    assert not user.has_perms(["accounts.view_user"])
    assert str(user) == "+998907654321"


@pytest.mark.django_db
def test_django_admin_is_open_to_admins_only(client: Client) -> None:
    admin = make_user(role=Role.ADMIN)
    client.force_login(admin)
    for url in (
        "/api/auth/django-admin/",
        "/api/auth/django-admin/accounts/user/",
        "/api/auth/django-admin/accounts/sellerapplication/",
        "/api/auth/django-admin/accounts/outbox/",
    ):
        assert client.get(url).status_code == 200, url

    client.force_login(make_user())
    assert client.get("/api/auth/django-admin/").status_code == 302


@pytest.mark.django_db
def test_models_render_readably() -> None:
    application = make_application(shop_name="Silk Road")
    otp_row = OtpCode.objects.create(
        phone="+998901234567", code_hash="x", expires_at=timezone.now()
    )
    event = Outbox.objects.create(event_id=uuid4(), event_type="seller.approved", payload={})

    assert str(application) == "Silk Road (pending)"
    assert str(otp_row) == "OTP for +998901234567"
    assert str(event) == f"seller.approved {event.event_id}"


def test_redis_client_is_built_once_from_settings(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(redis_client, "_client", None)
    settings.REDIS_URL = "redis://example.invalid:6379/3"

    client = redis_client.get_redis()

    assert isinstance(client, redis.Redis)
    assert client.connection_pool.connection_kwargs["db"] == 3
    assert redis_client.get_redis() is client
