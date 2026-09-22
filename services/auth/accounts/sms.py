"""Outgoing SMS behind a small interface; SMS_BACKEND picks the implementation."""

import logging
from typing import Protocol

from django.conf import settings

logger = logging.getLogger(__name__)


class SmsBackend(Protocol):
    def send(self, phone: str, text: str) -> None:
        """Deliver ``text`` to an E.164 ``phone`` or raise."""
        ...


class ConsoleSmsBackend:
    """Development backend: the message is written to the structured log, nothing is sent."""

    def send(self, phone: str, text: str) -> None:
        logger.info("sms (console backend)", extra={"phone": phone, "sms_text": text})


class EskizSmsBackend:
    """Eskiz.uz gateway. Waits for production credentials."""

    def __init__(self, email: str, password: str) -> None:
        self.email = email
        self.password = password

    def send(self, phone: str, text: str) -> None:
        raise NotImplementedError("The Eskiz SMS backend is not implemented yet.")


def get_sms_backend() -> SmsBackend:
    name = settings.SMS_BACKEND
    if name == "console":
        return ConsoleSmsBackend()
    if name == "eskiz":
        return EskizSmsBackend(settings.ESKIZ_EMAIL, settings.ESKIZ_PASSWORD)
    raise ValueError(f"Unknown SMS_BACKEND {name!r}")
