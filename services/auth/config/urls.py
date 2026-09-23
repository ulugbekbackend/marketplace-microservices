"""Health and metrics are served both at the root and behind the gateway prefix."""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.health import build_registry
from py_common.web.django import health_urlpatterns

registry = build_registry()

urlpatterns = [
    *health_urlpatterns(registry),
    *health_urlpatterns(registry, prefix="api/auth/"),
    path("api/auth/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/auth/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="docs",
    ),
    path("api/auth/django-admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
]
