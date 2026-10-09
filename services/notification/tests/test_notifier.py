"""Channels per contact, partial failures and the real channel implementations."""

import logging
from email import message_from_bytes
from typing import Any
from uuid import uuid4

import httpx
import pytest
from app.channels import ConsoleSmsChannel, EmailChannel, Message, TelegramChannel, sms_channel
from app.services.directory import Contact, Directory, DirectoryUnavailableError
from app.services.notifier import DeliveryError, Notifier, make_environment, render

from tests.conftest import FakeDirectory, FakeRedis, RecordingChannel, Sent

APPROVED = {"shop_name": "Do'kon", "url": "http://seller.test/"}


async def test_only_sms_without_email_or_telegram(
    notifier: Notifier, fake_directory: FakeDirectory, outbox: list[Sent]
) -> None:
    user = fake_directory.add_user()

    used = await notifier.notify(uuid4(), user, "seller_approved", APPROVED)

    assert used == ["sms"]
    assert [sent.channel for sent in outbox] == ["sms"]


async def test_every_filled_channel_is_used(
    notifier: Notifier, fake_directory: FakeDirectory, outbox: list[Sent]
) -> None:
    user = fake_directory.add_user(email="a@example.uz", telegram_chat_id="42")

    used = await notifier.notify(uuid4(), user, "seller_approved", APPROVED)

    assert used == ["sms", "email", "telegram"]
    assert {sent.message.subject for sent in outbox} == {"Do'koningiz tasdiqlandi"}


async def test_a_retry_skips_channels_that_already_delivered(
    notifier: Notifier,
    fake_directory: FakeDirectory,
    channels: list[RecordingChannel],
    outbox: list[Sent],
) -> None:
    user = fake_directory.add_user(email="a@example.uz")
    event_id = uuid4()
    channels[1].fail = True

    with pytest.raises(DeliveryError, match="email"):
        await notifier.notify(event_id, user, "seller_approved", APPROVED)
    assert [sent.channel for sent in outbox] == ["sms"]

    channels[1].fail = False
    assert await notifier.notify(event_id, user, "seller_approved", APPROVED) == ["email"]
    assert [sent.channel for sent in outbox] == ["sms", "email"]


def test_templates_render_subject_and_text() -> None:
    message = render(make_environment(), "seller_approved", APPROVED)

    assert message.subject == "Do'koningiz tasdiqlandi"
    assert message.text.splitlines()[-1] == "Kabinet: http://seller.test/"


def test_a_missing_template_variable_fails_loudly() -> None:
    with pytest.raises(Exception, match="url"):
        render(make_environment(), "seller_approved", {"shop_name": "X"})


# --- channels -------------------------------------------------------------------------

CONTACT = Contact(phone="+998901234567", email="a@example.uz", telegram_chat_id="42")
MESSAGE = Message(subject="Mavzu", text="Matn")


async def test_console_sms_logs_the_text(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        await ConsoleSmsChannel().send(CONTACT, MESSAGE)

    record = next(r for r in caplog.records if r.getMessage() == "sms (console backend)")
    assert record.__dict__["phone"] == "+998901234567"
    assert record.__dict__["sms_text"] == "Matn"


def test_unknown_sms_backend_is_refused() -> None:
    assert isinstance(sms_channel("console"), ConsoleSmsChannel)
    with pytest.raises(ValueError, match="eskiz"):
        sms_channel("eskiz")


async def test_email_goes_out_over_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, Any] = {}

    async def fake_send(message: Any, **kwargs: Any) -> None:
        sent["message"] = message
        sent.update(kwargs)

    monkeypatch.setattr("app.channels.aiosmtplib.send", fake_send)

    await EmailChannel("mailpit", 1025, "Bozorcha <no-reply@test>").send(CONTACT, MESSAGE)

    assert (sent["hostname"], sent["port"]) == ("mailpit", 1025)
    email = message_from_bytes(bytes(sent["message"]))
    assert (email["To"], email["Subject"]) == ("a@example.uz", "Mavzu")
    payload = email.get_payload(decode=True)
    assert isinstance(payload, bytes)
    assert payload.decode().strip() == "Matn"


async def test_telegram_posts_to_the_bot_api() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await TelegramChannel(http, "T0KEN").send(CONTACT, MESSAGE)

    [request] = calls
    assert request.url.path == "/botT0KEN/sendMessage"
    assert request.read() == b'{"chat_id":"42","text":"Matn"}'


@pytest.mark.parametrize(("status", "raises"), [(403, False), (400, False), (502, True)])
async def test_telegram_errors(status: int, raises: bool) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status))
    ) as http:
        channel = TelegramChannel(http, "T0KEN")
        if raises:
            with pytest.raises(httpx.HTTPStatusError):
                await channel.send(CONTACT, MESSAGE)
        else:
            await channel.send(CONTACT, MESSAGE)


async def test_telegram_without_a_token_only_logs() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await TelegramChannel(http, "").send(CONTACT, MESSAGE)


# --- directory ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [httpx.Response(500), httpx.Response(200, text="nope"), httpx.Response(200, json={"x": 1})],
)
async def test_directory_rejects_bad_answers(answer: httpx.Response) -> None:
    transport = httpx.MockTransport(lambda request: answer)
    async with httpx.AsyncClient(base_url="http://auth.test", transport=transport) as http:
        directory = Directory(http, http)
        with pytest.raises(DirectoryUnavailableError):
            await directory.contact(uuid4())
        with pytest.raises(DirectoryUnavailableError):
            await directory.customer_of(uuid4())


async def test_directory_maps_404_to_none(directory: Directory) -> None:
    assert await directory.contact(uuid4()) is None
    assert await directory.customer_of(uuid4()) is None


async def test_fake_redis_marks_are_kept(redis: FakeRedis) -> None:
    assert await redis.set("k", "1", nx=True) is True
    assert await redis.set("k", "1", nx=True) is None
