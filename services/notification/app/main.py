"""Notification service: tells customers and sellers about their orders (SMS, email, Telegram)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from decouple import config
from fastapi import FastAPI
from redis.asyncio import Redis

from app.channels import Channel, EmailChannel, TelegramChannel, sms_channel
from app.consumers.events import SERVICE, Links, NotificationEventHandler, build_router
from app.core.config import Settings, load_settings
from app.services.directory import Directory
from app.services.notifier import Notifier
from py_common.health import CheckFn, HealthRegistry
from py_common.idempotency import RedisIdempotencyStore
from py_common.logging import configure_logging
from py_common.rabbit import AioPikaConsumer, ConsumerRunner, broker_probe
from py_common.web.fastapi import setup

SERVICE_NAME = "notification"
API_PREFIX = "/api/notifications"

configure_logging(SERVICE_NAME, level=config("LOG_LEVEL", default="INFO"))
logger = logging.getLogger(__name__)


def redis_check(app: FastAPI) -> CheckFn:
    async def check() -> None:
        redis: Redis | None = getattr(app.state, "redis", None)
        if redis is None:
            raise RuntimeError("not started")
        await redis.ping()

    return check


def build_registry(app: FastAPI, settings: Settings) -> HealthRegistry:
    """Ready means Redis answers: without it events cannot be deduplicated."""
    registry = HealthRegistry()
    registry.add("redis", redis_check(app))
    if settings.rabbitmq_url:
        registry.add("rabbitmq", broker_probe(settings.rabbitmq_url))
    return registry


def build_channels(settings: Settings, http: httpx.AsyncClient) -> list[Channel]:
    return [
        sms_channel(settings.sms_backend),
        EmailChannel(settings.smtp_host, settings.smtp_port, settings.smtp_from),
        TelegramChannel(http, settings.telegram_bot_token),
    ]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    auth = httpx.AsyncClient(base_url=settings.auth_url, timeout=settings.http_timeout)
    orders = httpx.AsyncClient(base_url=settings.order_url, timeout=settings.http_timeout)
    telegram = httpx.AsyncClient(timeout=settings.http_timeout)
    directory = Directory(auth, orders)
    notifier = Notifier(directory, build_channels(settings, telegram), redis)
    router = build_router(
        RedisIdempotencyStore(redis, prefix=SERVICE),
        notifier,
        directory,
        Links(settings.shop_url, settings.seller_url),
    )
    app.state.redis = redis
    runner: ConsumerRunner | None = None
    if settings.consumer_enabled and settings.rabbitmq_url:
        runner = ConsumerRunner(
            AioPikaConsumer(settings.rabbitmq_url, SERVICE, NotificationEventHandler(router)),
            probe=broker_probe(settings.rabbitmq_url),
            name="notification-consumer",
        )
        runner.start()
    try:
        yield
    finally:
        if runner is not None:
            await runner.stop()
        for client in (auth, orders, telegram):
            await client.aclose()
        await redis.aclose()


def create_app(*, settings: Settings | None = None, with_lifespan: bool = True) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(
        title="Notification service",
        version="0.2.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        lifespan=lifespan if with_lifespan else None,
    )
    app.state.settings = settings
    setup(app, registry=build_registry(app, settings), api_prefix=API_PREFIX)
    return app


app = create_app()
