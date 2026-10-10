"""Settings read once from the environment (``.env`` is found by decouple)."""

from dataclasses import dataclass

from decouple import config


@dataclass(frozen=True, slots=True)
class Settings:
    redis_url: str
    rabbitmq_url: str
    consumer_enabled: bool
    auth_url: str
    order_url: str
    http_timeout: float
    sms_backend: str
    telegram_bot_token: str
    smtp_host: str
    smtp_port: int
    smtp_from: str
    shop_url: str
    seller_url: str


def load_settings() -> Settings:
    return Settings(
        redis_url=config("REDIS_URL", default="redis://redis:6379/0"),
        rabbitmq_url=config("RABBITMQ_URL", default=""),
        consumer_enabled=config("NOTIFICATION_CONSUMER_ENABLED", default=True, cast=bool),
        auth_url=config("AUTH_INTERNAL_URL", default="http://auth:8000"),
        order_url=config("ORDER_INTERNAL_URL", default="http://order:8000"),
        http_timeout=config("NOTIFICATION_HTTP_TIMEOUT", default=5.0, cast=float),
        sms_backend=config("SMS_BACKEND", default="console"),
        telegram_bot_token=config("TELEGRAM_BOT_TOKEN", default=""),
        smtp_host=config("SMTP_HOST", default="mailpit"),
        smtp_port=config("SMTP_PORT", default=1025, cast=int),
        smtp_from=config("SMTP_FROM", default="Bozorcha <no-reply@bozorcha.local>"),
        shop_url=config("SHOP_URL", default="http://shop.localhost"),
        seller_url=config("SELLER_URL", default="http://seller.localhost"),
    )
