"""Settings read once from the environment (``.env`` is found by decouple)."""

from dataclasses import dataclass

from decouple import config


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    rabbitmq_url: str
    consumer_enabled: bool
    relay_enabled: bool
    relay_interval_seconds: float
    payout_scheduler_enabled: bool
    order_url: str
    order_timeout: float
    shop_url: str
    mock_enabled: bool
    payme_merchant_id: str
    payme_key: str
    payme_checkout_url: str
    click_merchant_id: str
    click_service_id: str
    click_secret_key: str
    click_checkout_url: str


def database_url() -> str:
    user = config("PAYMENT_DB_USER", default="payment_user")
    password = config("DB_PASSWORD", default="")
    host = config("POSTGRES_HOST", default="postgres")
    port = config("POSTGRES_PORT", default=5432, cast=int)
    name = config("PAYMENT_DB_NAME", default="payment_db")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


def load_settings() -> Settings:
    return Settings(
        database_url=database_url(),
        rabbitmq_url=config("RABBITMQ_URL", default=""),
        consumer_enabled=config("PAYMENT_CONSUMER_ENABLED", default=True, cast=bool),
        relay_enabled=config("PAYMENT_RELAY_ENABLED", default=True, cast=bool),
        relay_interval_seconds=config("PAYMENT_RELAY_INTERVAL", default=1.0, cast=float),
        payout_scheduler_enabled=config("PAYOUT_SCHEDULER_ENABLED", default=True, cast=bool),
        order_url=config("ORDER_INTERNAL_URL", default="http://order:8000"),
        order_timeout=config("ORDER_TIMEOUT", default=5.0, cast=float),
        shop_url=config("SHOP_URL", default="http://shop.localhost"),
        mock_enabled=config("PAYMENT_MOCK_ENABLED", default=False, cast=bool),
        payme_merchant_id=config("PAYME_MERCHANT_ID", default=""),
        payme_key=config("PAYME_KEY", default=""),
        payme_checkout_url=config("PAYME_CHECKOUT_URL", default=""),
        click_merchant_id=config("CLICK_MERCHANT_ID", default=""),
        click_service_id=config("CLICK_SERVICE_ID", default=""),
        click_secret_key=config("CLICK_SECRET_KEY", default=""),
        click_checkout_url=config("CLICK_CHECKOUT_URL", default=""),
    )
