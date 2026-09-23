"""OpenAPI extensions: describe how callers authenticate through the gateway."""

from typing import Any

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class GatewayAuthenticationScheme(OpenApiAuthenticationExtension):  # type: ignore[no-untyped-call]
    """Clients send a bearer JWT to the gateway; the service only sees identity headers."""

    target_class = "py_common.web.drf.GatewayAuthentication"
    name = "bearerAuth"

    def get_security_definition(self, auto_schema: Any) -> dict[str, str]:
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
