"""Readiness checks: the service is ready when its dependencies answer."""

import redis.asyncio as redis_async
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import connections

from py_common.health import HealthRegistry


def _ping_database() -> None:
    """Open a connection of this thread's own, so no connection is shared across threads."""
    connection = connections.create_connection("default")
    try:
        connection.ensure_connection()
    finally:
        connection.close()


async def _database() -> None:
    await sync_to_async(_ping_database, thread_sensitive=False)()


async def _redis() -> None:
    """OTP rate limits live in Redis, so sign in cannot work without it."""
    client = redis_async.Redis.from_url(settings.REDIS_URL)
    try:
        await client.ping()
    finally:
        await client.aclose()


def build_registry() -> HealthRegistry:
    registry = HealthRegistry()
    registry.add("postgres", _database)
    registry.add("redis", _redis)
    return registry
