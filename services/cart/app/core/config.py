"""Settings read once from the environment (``.env`` is found by decouple)."""

from dataclasses import dataclass

from decouple import config


@dataclass(frozen=True, slots=True)
class Settings:
    redis_url: str
    catalog_url: str
    catalog_timeout: float
    catalog_cache_seconds: int
    cart_ttl_seconds: int
    max_qty: int
    max_lines: int
    max_favorites: int
    guest_cookie: str
    guest_cookie_secure: bool


def load_settings() -> Settings:
    return Settings(
        redis_url=config("REDIS_URL", default="redis://redis:6379/0"),
        catalog_url=config("CATALOG_INTERNAL_URL", default="http://catalog:8000"),
        catalog_timeout=config("CATALOG_TIMEOUT", default=3.0, cast=float),
        catalog_cache_seconds=config("CART_CATALOG_CACHE_SECONDS", default=30, cast=int),
        cart_ttl_seconds=config("CART_TTL_SECONDS", default=30 * 24 * 3600, cast=int),
        max_qty=99,
        max_lines=100,
        max_favorites=500,
        guest_cookie="guest_id",
        guest_cookie_secure=config("COOKIE_SECURE", default=False, cast=bool),
    )
