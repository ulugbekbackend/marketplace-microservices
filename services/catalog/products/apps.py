from django.apps import AppConfig


class ProductsConfig(AppConfig):
    name = "products"

    def ready(self) -> None:
        # Registers the OpenAPI description of gateway authentication.
        from config import schema  # noqa: F401
