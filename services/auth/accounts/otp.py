"""Sign in by one time password sent over SMS.

Codes are 6 digits, stored as an HMAC (keyed with SECRET_KEY, bound to the phone), live
OTP_TTL_SECONDS and die after OTP_MAX_ATTEMPTS wrong guesses. A phone gets at most one code
per OTP_RESEND_SECONDS, enforced in Redis with SET NX EX.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta
from enum import StrEnum

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from accounts.models import OtpCode, User
from accounts.phone import InvalidPhoneError, normalize_phone
from accounts.redis_client import get_redis
from accounts.sms import get_sms_backend
from accounts.tokens import TokenPair, issue_tokens
from py_common.web.drf import ApiError

logger = logging.getLogger(__name__)


def resend_key(phone: str) -> str:
    return f"auth:otp:resend:{phone}"


def hash_code(phone: str, code: str) -> str:
    message = f"{phone}:{code}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def generate_code() -> str:
    return f"{secrets.randbelow(10**settings.OTP_LENGTH):0{settings.OTP_LENGTH}d}"


def parse_phone(raw: str) -> str:
    try:
        return normalize_phone(raw)
    except InvalidPhoneError as exc:
        raise ApiError("INVALID_PHONE", str(exc), details={"phone": raw}) from exc


def send_code(raw_phone: str) -> None:
    phone = parse_phone(raw_phone)
    redis = get_redis()
    key = resend_key(phone)
    if not redis.set(key, "1", nx=True, ex=settings.OTP_RESEND_SECONDS):
        retry_after = max(int(redis.ttl(key)), 1)
        raise ApiError(
            "OTP_RATE_LIMITED",
            "A code was sent recently. Try again later.",
            status=429,
            details={"retry_after": retry_after},
        )

    code = generate_code()
    now = timezone.now()
    with transaction.atomic():
        # Only the newest code is valid: older ones are dropped with their attempt counters.
        OtpCode.objects.filter(phone=phone).delete()
        OtpCode.objects.create(
            phone=phone,
            code_hash=hash_code(phone, code),
            expires_at=now + timedelta(seconds=settings.OTP_TTL_SECONDS),
            created_at=now,
        )

    try:
        get_sms_backend().send(phone, f"Marketplace: your sign in code is {code}")
    except Exception as exc:
        redis.delete(key)  # let the user ask again at once, nothing reached them
        logger.exception("sms sending failed", extra={"phone": phone})
        raise ApiError(
            "SMS_FAILED", "The code could not be sent. Try again later.", status=502
        ) from exc


class _Outcome(StrEnum):
    OK = "ok"
    MISSING = "missing"
    EXPIRED = "expired"
    BLOCKED = "blocked"
    WRONG = "wrong"


def _check_code(phone: str, code: str) -> tuple[_Outcome, int]:
    """Compare against the newest code under a row lock; returns the outcome and attempts left.

    A wrong guess is committed here, before the caller raises, so it always counts.
    """
    if settings.DEBUG and code == settings.OTP_MASTER_CODE:
        OtpCode.objects.filter(phone=phone).delete()
        return _Outcome.OK, 0

    with transaction.atomic():
        otp = (
            OtpCode.objects.select_for_update().filter(phone=phone).order_by("-created_at").first()
        )
        if otp is None:
            return _Outcome.MISSING, 0
        if otp.attempts >= settings.OTP_MAX_ATTEMPTS:
            return _Outcome.BLOCKED, 0
        if otp.expires_at <= timezone.now():
            return _Outcome.EXPIRED, 0
        if not hmac.compare_digest(otp.code_hash, hash_code(phone, code)):
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            return _Outcome.WRONG, settings.OTP_MAX_ATTEMPTS - otp.attempts
        otp.delete()  # a code signs in once
        return _Outcome.OK, 0


def verify_code(raw_phone: str, code: str) -> tuple[User, TokenPair]:
    """Check the code, create the user on the first sign in and issue a token pair."""
    phone = parse_phone(raw_phone)
    outcome, attempts_left = _check_code(phone, code)
    if outcome is _Outcome.MISSING:
        raise ApiError("OTP_INVALID", "Wrong code. Request a new code.")
    if outcome is _Outcome.BLOCKED:
        raise ApiError("OTP_BLOCKED", "Too many wrong attempts. Request a new code.", status=429)
    if outcome is _Outcome.EXPIRED:
        raise ApiError("OTP_EXPIRED", "The code has expired. Request a new code.")
    if outcome is _Outcome.WRONG:
        raise ApiError("OTP_INVALID", "Wrong code.", details={"attempts_left": attempts_left})

    with transaction.atomic():
        user, created = User.objects.get_or_create(
            phone=phone, defaults={"password": make_password(None)}
        )
        if created:
            logger.info("user registered", extra={"user_id": str(user.id)})
        if not user.is_active:
            raise ApiError("USER_INACTIVE", "This account is disabled.", status=403)
        return user, issue_tokens(user)
