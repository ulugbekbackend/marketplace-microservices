"""Shared fixtures: auth and order internal APIs behind ``httpx.MockTransport``, an in-memory
Redis and channels that record what they would have sent."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from app.channels import Message
from app.consumers.events import Links, build_router
from app.services.directory import Contact, Directory
from app.services.notifier import Notifier

from contracts.events import Frozen, build_event
from py_common.consumer import EventRouter
from py_common.idempotency import RedisIdempotencyStore

SHOP = "http://shop.test"
SELLER = "http://seller.test"


class FakeRedis:
    """The few commands the service uses: SET NX EX, GET, DELETE."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def set(
        self, key: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool | None:
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def delete(self, *keys: str) -> int:
        return sum(self.data.pop(key, None) is not None for key in keys)


@dataclass
class Sent:
    channel: str
    contact: Contact
    message: Message


@dataclass
class RecordingChannel:
    name: str
    field_name: str
    outbox: list[Sent]
    fail: bool = False

    def applies_to(self, contact: Contact) -> bool:
        return bool(getattr(contact, self.field_name))

    async def send(self, contact: Contact, message: Message) -> None:
        if self.fail:
            raise ConnectionError(f"{self.name} is down")
        self.outbox.append(Sent(self.name, contact, message))


@dataclass
class FakeDirectory:
    """Users by id and order owners; ``mode`` "down" makes every lookup fail."""

    users: dict[UUID, dict[str, str]] = field(default_factory=dict)
    order_owners: dict[UUID, UUID] = field(default_factory=dict)
    mode: str = "ok"

    def add_user(self, **contact: str) -> UUID:
        user_id = uuid4()
        self.users[user_id] = {"phone": "+998901234567", **contact}
        return user_id

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.mode == "down":
            raise httpx.ConnectError("down", request=request)
        parts = request.url.path.strip("/").split("/")
        if parts[:3] == ["internal", "auth", "users"]:
            user = self.users.get(UUID(parts[3]))
            return httpx.Response(200, json=user) if user else httpx.Response(404)
        if parts[:2] == ["internal", "orders"]:
            owner = self.order_owners.get(UUID(parts[2]))
            if owner is None:
                return httpx.Response(404)
            return httpx.Response(200, json={"payable": False, "customer_id": str(owner)})
        return httpx.Response(404)


@pytest.fixture
def fake_directory() -> FakeDirectory:
    return FakeDirectory()


@pytest.fixture
async def directory(fake_directory: FakeDirectory) -> AsyncIterator[Directory]:
    transport = httpx.MockTransport(fake_directory.handler)
    async with (
        httpx.AsyncClient(base_url="http://auth.test", transport=transport) as auth,
        httpx.AsyncClient(base_url="http://order.test", transport=transport) as orders,
    ):
        yield Directory(auth, orders)


@pytest.fixture
def outbox() -> list[Sent]:
    return []


@pytest.fixture
def channels(outbox: list[Sent]) -> list[RecordingChannel]:
    return [
        RecordingChannel("sms", "phone", outbox),
        RecordingChannel("email", "email", outbox),
        RecordingChannel("telegram", "telegram_chat_id", outbox),
    ]


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def notifier(directory: Directory, channels: list[RecordingChannel], redis: FakeRedis) -> Notifier:
    return Notifier(directory, channels, redis)  # type: ignore[arg-type]


@pytest.fixture
def router(notifier: Notifier, directory: Directory, redis: FakeRedis) -> EventRouter:
    store = RedisIdempotencyStore(redis, prefix="notification")
    return build_router(store, notifier, directory, Links(SHOP, SELLER))


def body(payload: Frozen, *, event_id: UUID | None = None) -> bytes:
    envelope = build_event(
        payload,
        producer="test",
        correlation_id=uuid4(),
        occurred_at=datetime.now(UTC),
        event_id=event_id,
    )
    return envelope.model_dump_json().encode()


def texts(outbox: list[Sent], channel: str = "sms") -> list[str]:
    return [sent.message.text for sent in outbox if sent.channel == channel]


def recipients(outbox: list[Sent]) -> list[tuple[str, str]]:
    return [(sent.channel, sent.contact.phone) for sent in outbox]
