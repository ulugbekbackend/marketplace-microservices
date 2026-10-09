"""Shared fixtures. Tests run against a real Postgres database built by the Alembic
migrations; the order service is an in-process fake behind ``httpx.MockTransport``."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from alembic import command
from alembic.config import Config
from app.core.config import Settings, load_settings
from app.db import make_engine, make_sessionmaker
from app.main import create_app, wire
from app.models import Base, Outbox
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from contracts.enums import OrderStatus, UserRole
from contracts.headers import X_SELLER_ID, X_USER_ID, X_USER_ROLE

ORDER_URL = "http://order.test"
TEST_DB = "payment_test_db"
PAYME_KEY = "test-payme-key"
CLICK_SECRET = "test-click-secret"
CLICK_SERVICE_ID = "777"


async def _recreate_database(url: str) -> None:
    connection = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await connection.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        await connection.execute(f"CREATE DATABASE {TEST_DB}")
    finally:
        await connection.close()


@pytest.fixture(scope="session")
def database_url() -> str:
    """A fresh test database migrated to head (the migrations are under test too)."""
    base = load_settings().database_url
    asyncio.run(_recreate_database(base))
    url = base.rsplit("/", 1)[0] + "/" + TEST_DB
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    return url


@pytest.fixture(scope="session")
def settings(database_url: str) -> Settings:
    return replace(
        load_settings(),
        database_url=database_url,
        rabbitmq_url="",
        order_url=ORDER_URL,
        shop_url="http://shop.test",
        mock_enabled=True,
        payme_merchant_id="merchant-1",
        payme_key=PAYME_KEY,
        payme_checkout_url="",
        click_merchant_id="click-merchant",
        click_service_id=CLICK_SERVICE_ID,
        click_secret_key=CLICK_SECRET,
        click_checkout_url="",
    )


@pytest.fixture(scope="session")
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = make_engine(settings.database_url)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return make_sessionmaker(engine)


@pytest.fixture(autouse=True)
async def clean_tables(engine: AsyncEngine) -> AsyncIterator[None]:
    yield
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


# --- order service fake ---------------------------------------------------------------


class FakeOrders:
    """``/internal/orders/{id}/payable/``. ``mode``: "ok", "down", "error"."""

    def __init__(self) -> None:
        self.orders: dict[UUID, dict[str, Any]] = {}
        self.mode = "ok"
        self.calls = 0

    def add(
        self,
        *,
        amount_tiyin: int = 1_500_000,
        status: OrderStatus = OrderStatus.RESERVED,
        customer_id: UUID | None = None,
    ) -> UUID:
        order_id = uuid4()
        self.orders[order_id] = {
            "payable": status is OrderStatus.RESERVED,
            "amount_tiyin": amount_tiyin,
            "status": status.value,
            "customer_id": str(customer_id or uuid4()),
            "reserved_until": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
        }
        return order_id

    def set_status(self, order_id: UUID, status: OrderStatus) -> None:
        self.orders[order_id]["status"] = status.value
        self.orders[order_id]["payable"] = status is OrderStatus.RESERVED

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.mode == "down":
            raise httpx.ConnectError("order service is down", request=request)
        if self.mode == "error":
            return httpx.Response(500)
        parts = request.url.path.strip("/").split("/")
        if parts[:2] != ["internal", "orders"] or parts[3:] != ["payable"]:
            return httpx.Response(404)
        order = self.orders.get(UUID(parts[2]))
        if order is None:
            return httpx.Response(404, json={"error": {"code": "NOT_FOUND"}})
        return httpx.Response(200, json=order)


class Clock:
    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def orders() -> FakeOrders:
    return FakeOrders()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
async def app(
    settings: Settings, engine: AsyncEngine, orders: FakeOrders, clock: Clock
) -> AsyncIterator[FastAPI]:
    app = create_app(settings=settings, with_lifespan=False)
    http = httpx.AsyncClient(base_url=ORDER_URL, transport=httpx.MockTransport(orders.handler))
    wire(app, settings, engine, http, clock=clock)
    yield app
    await http.aclose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def user_headers(
    user_id: UUID, role: UserRole = UserRole.CUSTOMER, seller_id: UUID | None = None
) -> dict[str, str]:
    headers = {X_USER_ID: str(user_id), X_USER_ROLE: role.value}
    if seller_id is not None:
        headers[X_SELLER_ID] = str(seller_id)
    return headers


async def outbox_events(sessions: async_sessionmaker[AsyncSession]) -> list[Outbox]:
    async with sessions() as session:
        return list((await session.scalars(select(Outbox).order_by(Outbox.id))).all())
