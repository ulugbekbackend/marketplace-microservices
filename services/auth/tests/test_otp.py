import logging
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import fakeredis
import pytest
from django.utils import timezone
from pytest_django import Settings
from rest_framework.test import APIClient

from accounts import otp
from accounts.models import OtpCode, Role, User
from accounts.sms import ConsoleSmsBackend, EskizSmsBackend, get_sms_backend
from tests.factories import make_user

pytestmark = pytest.mark.django_db

PHONE = "+998901234567"
SEND = "/api/auth/otp/send/"
VERIFY = "/api/auth/otp/verify/"


def send(api: APIClient, phone: str = PHONE, code: str = "123456") -> str:
    """Request a code with a known value and return it."""
    with patch.object(otp, "generate_code", return_value=code):
        response = api.post(SEND, {"phone": phone}, format="json")
    assert response.status_code == 204, response.content
    return code


def verify(api: APIClient, code: str, phone: str = PHONE) -> Any:
    return api.post(VERIFY, {"phone": phone, "code": code}, format="json")


def error_code(response: Any) -> str:
    return str(response.json()["error"]["code"])


def test_happy_path_creates_the_user_and_returns_tokens(api: APIClient) -> None:
    code = send(api, "90 123 45 67")

    response = verify(api, code, "+998 90 123 45 67")

    assert response.status_code == 200
    body = response.json()
    assert body["access"] and body["refresh"]
    assert body["user"]["phone"] == PHONE
    assert body["user"]["role"] == Role.CUSTOMER
    user = User.objects.get(phone=PHONE)
    assert str(user.id) == body["user"]["id"]
    assert not user.has_usable_password()


def test_second_sign_in_reuses_the_account(api: APIClient, fake_redis: fakeredis.FakeRedis) -> None:
    verify(api, send(api))
    fake_redis.flushall()

    response = verify(api, send(api))

    assert response.status_code == 200
    assert User.objects.filter(phone=PHONE).count() == 1


def test_code_is_stored_hashed_and_logged_by_console_backend(
    api: APIClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="accounts.sms"):
        api.post(SEND, {"phone": PHONE}, format="json")

    record = next(r for r in caplog.records if r.name == "accounts.sms")
    assert record.__dict__["phone"] == PHONE
    code = record.__dict__["sms_text"].rsplit(" ", 1)[-1]
    assert len(code) == 6 and code.isdigit()
    stored = OtpCode.objects.get(phone=PHONE)
    assert code not in stored.code_hash
    assert stored.code_hash == otp.hash_code(PHONE, code)
    assert verify(api, code).status_code == 200


def test_code_expires(api: APIClient) -> None:
    code = send(api)
    OtpCode.objects.filter(phone=PHONE).update(expires_at=timezone.now() - timedelta(seconds=1))

    response = verify(api, code)

    assert response.status_code == 400
    assert error_code(response) == "OTP_EXPIRED"


def test_code_lives_two_minutes(api: APIClient) -> None:
    before = timezone.now()
    send(api)

    otp_row = OtpCode.objects.get(phone=PHONE)
    assert timedelta(seconds=119) < otp_row.expires_at - before <= timedelta(seconds=121)


def test_wrong_code_counts_attempts_and_blocks_after_five(api: APIClient) -> None:
    code = send(api)

    attempts_left = []
    for _ in range(5):
        response = verify(api, "999999")
        assert response.status_code == 400
        assert error_code(response) == "OTP_INVALID"
        attempts_left.append(response.json()["error"]["details"]["attempts_left"])

    assert attempts_left == [4, 3, 2, 1, 0]
    blocked = verify(api, code)  # even the right code is refused now
    assert blocked.status_code == 429
    assert error_code(blocked) == "OTP_BLOCKED"
    assert OtpCode.objects.get(phone=PHONE).attempts == 5
    assert not User.objects.filter(phone=PHONE).exists()


def test_a_new_code_replaces_a_blocked_one(api: APIClient, fake_redis: fakeredis.FakeRedis) -> None:
    send(api)
    for _ in range(5):
        verify(api, "999999")
    fake_redis.flushall()

    code = send(api, code="654321")

    assert verify(api, code).status_code == 200


def test_code_works_only_once(api: APIClient) -> None:
    code = send(api)
    assert verify(api, code).status_code == 200

    again = verify(api, code)

    assert again.status_code == 400
    assert error_code(again) == "OTP_INVALID"


def test_verify_without_a_sent_code_is_invalid(api: APIClient) -> None:
    response = verify(api, "123456")

    assert response.status_code == 400
    assert error_code(response) == "OTP_INVALID"


def test_resend_is_rate_limited_for_sixty_seconds(
    api: APIClient, fake_redis: fakeredis.FakeRedis
) -> None:
    send(api)

    response = api.post(SEND, {"phone": "901234567"}, format="json")

    assert response.status_code == 429
    assert error_code(response) == "OTP_RATE_LIMITED"
    assert 0 < response.json()["error"]["details"]["retry_after"] <= 60
    assert 0 < fake_redis.ttl(otp.resend_key(PHONE)) <= 60
    assert OtpCode.objects.filter(phone=PHONE).count() == 1


def test_rate_limit_is_per_phone(api: APIClient) -> None:
    send(api)

    assert api.post(SEND, {"phone": "+998911234567"}, format="json").status_code == 204


def test_resend_allowed_once_the_window_passed(
    api: APIClient, fake_redis: fakeredis.FakeRedis
) -> None:
    send(api)
    fake_redis.delete(otp.resend_key(PHONE))  # what Redis does when the 60 s TTL runs out

    assert api.post(SEND, {"phone": PHONE}, format="json").status_code == 204


def test_master_code_works_in_debug(api: APIClient, settings: Settings) -> None:
    settings.DEBUG = True

    response = verify(api, "000000")

    assert response.status_code == 200
    assert User.objects.filter(phone=PHONE).exists()


def test_master_code_is_rejected_without_debug(api: APIClient, settings: Settings) -> None:
    settings.DEBUG = False
    send(api)

    response = verify(api, "000000")

    assert response.status_code == 400
    assert error_code(response) == "OTP_INVALID"
    assert not User.objects.filter(phone=PHONE).exists()


@pytest.mark.parametrize(
    ("url", "body"),
    [(SEND, {"phone": "12345"}), (VERIFY, {"phone": "12345", "code": "123456"})],
)
def test_invalid_phone_is_rejected(api: APIClient, url: str, body: dict[str, str]) -> None:
    response = api.post(url, body, format="json")

    assert response.status_code == 400
    assert error_code(response) == "INVALID_PHONE"


def test_code_must_be_six_digits(api: APIClient) -> None:
    response = verify(api, "12ab")

    assert response.status_code == 400
    assert error_code(response) == "VALIDATION_ERROR"
    assert "code" in response.json()["error"]["details"]


def test_inactive_user_cannot_sign_in(api: APIClient) -> None:
    make_user(phone=PHONE, is_active=False)

    response = verify(api, send(api))

    assert response.status_code == 403
    assert error_code(response) == "USER_INACTIVE"


def test_sms_failure_returns_502_and_frees_the_rate_limit(
    api: APIClient, fake_redis: fakeredis.FakeRedis
) -> None:
    with patch.object(ConsoleSmsBackend, "send", side_effect=RuntimeError("down")):
        response = api.post(SEND, {"phone": PHONE}, format="json")

    assert response.status_code == 502
    assert error_code(response) == "SMS_FAILED"
    assert fake_redis.get(otp.resend_key(PHONE)) is None


def test_sms_backend_selection(settings: Settings) -> None:
    settings.SMS_BACKEND = "console"
    assert isinstance(get_sms_backend(), ConsoleSmsBackend)

    settings.SMS_BACKEND = "eskiz"
    backend = get_sms_backend()
    assert isinstance(backend, EskizSmsBackend)
    with pytest.raises(NotImplementedError):
        backend.send(PHONE, "hi")

    settings.SMS_BACKEND = "carrier-pigeon"
    with pytest.raises(ValueError, match="Unknown SMS_BACKEND"):
        get_sms_backend()


def test_generated_codes_are_six_digits() -> None:
    codes = {otp.generate_code() for _ in range(50)}

    assert all(len(code) == 6 and code.isdigit() for code in codes)
    assert len(codes) > 1
