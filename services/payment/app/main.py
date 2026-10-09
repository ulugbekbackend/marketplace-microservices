"""Payment service: Payme and Click callbacks, the mock provider, refunds and payouts."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from decouple import config
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api import payments, providers, seller
from app.consumers.events import SERVICE, PaymentEventHandler
from app.core.config import Settings, load_settings
from app.db import make_engine, make_sessionmaker
from app.outbox import OutboxRelay
from app.payouts import PayoutScheduler
from app.providers.click import ClickShop
from app.providers.payme import PaymeMerchant
from app.services.orders import OrderClient
from app.services.payments import utcnow
from py_common.health import CheckFn, HealthRegistry
from py_common.logging import configure_logging
from py_common.rabbit import AioPikaConsumer, AioPikaPublisher, ConsumerRunner, broker_probe
from py_common.web.fastapi import setup

SERVICE_NAME = "payment"
API_PREFIX = "/api/payments"

configure_logging(SERVICE_NAME, level=config("LOG_LEVEL", default="INFO"))
logger = logging.getLogger(__name__)


def database_check(app: FastAPI) -> CheckFn:
    async def check() -> None:
        engine: AsyncEngine | None = getattr(app.state, "engine", None)
        if engine is None:
            raise RuntimeError("not started")
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    return check


def build_registry(app: FastAPI, settings: Settings) -> HealthRegistry:
    """Ready means the database answers: callbacks cannot be served without it."""
    registry = HealthRegistry()
    registry.add("postgres", database_check(app))
    if settings.rabbitmq_url:
        registry.add("rabbitmq", broker_probe(settings.rabbitmq_url))
    return registry


def wire(
    app: FastAPI,
    settings: Settings,
    engine: AsyncEngine,
    http: httpx.AsyncClient,
    *,
    clock: Callable[[], datetime] = utcnow,
) -> None:
    """Build the services once and keep them on the application state."""
    sessions = make_sessionmaker(engine)
    orders = OrderClient(http)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = sessions
    app.state.orders = orders
    app.state.payme = PaymeMerchant(sessions, orders, key=settings.payme_key, clock=clock)
    app.state.click = ClickShop(
        sessions,
        orders,
        service_id=settings.click_service_id,
        secret_key=settings.click_secret_key,
        clock=clock,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = make_engine(settings.database_url)
    http = httpx.AsyncClient(base_url=settings.order_url, timeout=settings.order_timeout)
    wire(app, settings, engine, http)

    publisher: AioPikaPublisher | None = None
    relay: OutboxRelay | None = None
    if settings.rabbitmq_url and settings.relay_enabled:
        publisher = AioPikaPublisher(settings.rabbitmq_url)
        relay = OutboxRelay(app.state.sessions, publisher, interval=settings.relay_interval_seconds)
        relay.start()
    runner: ConsumerRunner | None = None
    if settings.rabbitmq_url and settings.consumer_enabled:
        runner = ConsumerRunner(
            AioPikaConsumer(
                settings.rabbitmq_url, SERVICE, PaymentEventHandler(app.state.sessions)
            ),
            probe=broker_probe(settings.rabbitmq_url),
            name="payment-consumer",
        )
        runner.start()
    scheduler: PayoutScheduler | None = None
    if settings.payout_scheduler_enabled:
        scheduler = PayoutScheduler(app.state.sessions)
        scheduler.start()
    try:
        yield
    finally:
        if scheduler is not None:
            await scheduler.stop()
        if runner is not None:
            await runner.stop()
        if relay is not None:
            await relay.stop()
        if publisher is not None:
            await publisher.close()
        await http.aclose()
        await engine.dispose()


def create_app(*, settings: Settings | None = None, with_lifespan: bool = True) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(
        title="Payment service",
        version="0.2.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        lifespan=lifespan if with_lifespan else None,
    )
    app.state.settings = settings
    setup(app, registry=build_registry(app, settings), api_prefix=API_PREFIX)
    app.include_router(payments.router)
    app.include_router(providers.router)
    app.include_router(seller.router)
    return app


app = create_app()
