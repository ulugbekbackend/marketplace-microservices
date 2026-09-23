"""One Redis client per process, created on first use from REDIS_URL."""

import redis
from django.conf import settings

_client: "redis.Redis | None" = None


def get_redis() -> "redis.Redis":
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client
