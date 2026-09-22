from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "accounts"
    verbose_name = "Accounts"

    def ready(self) -> None:
        # Registers the OpenAPI description of the gateway authentication.
        from accounts import schema  # noqa: F401
