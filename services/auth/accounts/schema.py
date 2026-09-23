"""OpenAPI description of the gateway identity, so documented endpoints show their auth."""

from typing import Any

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class GatewayAuthenticationScheme(OpenApiAuthenticationExtension):  # type: ignore[no-untyped-call]
    target_class = "py_common.web.drf.GatewayAuthentication"
    name = "gatewayBearer"

    def get_security_definition(self, auto_schema: Any) -> dict[str, Any]:
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Access token; the gateway verifies it and forwards the identity.",
        }
