"""Readiness checks: the service is ready when its dependencies answer."""

from asgiref.sync import sync_to_async
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


def build_registry() -> HealthRegistry:
    registry = HealthRegistry()
    registry.add("postgres", _database)
    return registry
