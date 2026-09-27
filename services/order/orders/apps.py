from django.apps import AppConfig


class OrdersConfig(AppConfig):
    name = "orders"

    def ready(self) -> None:
        # Registers the OpenAPI description of gateway authentication.
        from config import schema  # noqa: F401
