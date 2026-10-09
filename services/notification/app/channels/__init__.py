"""Delivery channels. SMS always applies (every user has a phone); email and Telegram only
when the user filled them in. A channel raises when delivery fails, so the event is retried.
"""

import logging
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib
import httpx

from app.services.directory import Contact

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


@dataclass(frozen=True, slots=True)
class Message:
    subject: str
    text: str


class Channel(Protocol):
    name: str

    def applies_to(self, contact: Contact) -> bool: ...

    async def send(self, contact: Contact, message: Message) -> None: ...


class ConsoleSmsChannel:
    """Development SMS: the text goes to the log, nothing leaves the machine."""

    name = "sms"

    def applies_to(self, contact: Contact) -> bool:
        return bool(contact.phone)

    async def send(self, contact: Contact, message: Message) -> None:
        logger.info(
            "sms (console backend)", extra={"phone": contact.phone, "sms_text": message.text}
        )


class EmailChannel:
    """SMTP; in development the stack's Mailpit catches every message."""

    name = "email"

    def __init__(self, host: str, port: int, sender: str) -> None:
        self._host = host
        self._port = port
        self._sender = sender

    def applies_to(self, contact: Contact) -> bool:
        return bool(contact.email)

    async def send(self, contact: Contact, message: Message) -> None:
        email = EmailMessage()
        email["From"] = self._sender
        email["To"] = contact.email
        email["Subject"] = message.subject
        email.set_content(message.text)
        await aiosmtplib.send(email, hostname=self._host, port=self._port, timeout=10)


class TelegramChannel:
    """Bot API ``sendMessage``. Without a bot token the message is only logged."""

    name = "telegram"

    def __init__(self, http: httpx.AsyncClient, token: str) -> None:
        self._http = http
        self._token = token

    def applies_to(self, contact: Contact) -> bool:
        return bool(contact.telegram_chat_id)

    async def send(self, contact: Contact, message: Message) -> None:
        if not self._token:
            logger.info(
                "telegram (no bot token)",
                extra={"chat_id": contact.telegram_chat_id, "telegram_text": message.text},
            )
            return
        response = await self._http.post(
            f"{TELEGRAM_API}/bot{self._token}/sendMessage",
            json={"chat_id": contact.telegram_chat_id, "text": message.text},
        )
        if response.status_code == 400 or response.status_code == 403:
            # Unknown chat or the user blocked the bot: retrying cannot help.
            logger.warning(
                "telegram refused the message",
                extra={"chat_id": contact.telegram_chat_id, "status": response.status_code},
            )
            return
        response.raise_for_status()


def sms_channel(backend: str) -> Channel:
    if backend == "console":
        return ConsoleSmsChannel()
    raise ValueError(f"unknown SMS backend {backend!r}: only 'console' is available")
