"""Health and metrics are served both at the root and behind the gateway prefix."""

from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.health import build_registry
from py_common.web.django import health_urlpatterns

registry = build_registry()

urlpatterns = [
    *health_urlpatterns(registry),
    *health_urlpatterns(registry, prefix="api/orders/"),
    path("api/orders/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/orders/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="docs",
    ),
]
