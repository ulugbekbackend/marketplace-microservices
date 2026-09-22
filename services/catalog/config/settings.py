"""Settings for the catalog service. One file, values come from the environment."""

from pathlib import Path

from decouple import config

from py_common.logging import configure_logging

BASE_DIR = Path(__file__).resolve().parent.parent
SERVICE_NAME = "catalog"

SECRET_KEY = config("SECRET_KEY", default="dev-only-not-secret")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="*").split(",")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
]

MIDDLEWARE = [
    "py_common.web.django.correlation_id_middleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

DATABASES: dict[str, dict[str, object]] = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("CATALOG_DB_NAME", default="catalog_db"),
        "USER": config("CATALOG_DB_USER", default="catalog_user"),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("POSTGRES_HOST", default="postgres"),
        "PORT": config("POSTGRES_PORT", default=5432, cast=int),
        "CONN_MAX_AGE": 60,
    }
}

REST_FRAMEWORK: dict[str, object] = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS: dict[str, object] = {
    "TITLE": "Catalog service",
    "VERSION": "0.1.0",
    "SCHEMA_PATH_PREFIX": "/api/catalog",
    "SERVE_INCLUDE_SCHEMA": False,
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
STATIC_URL = "static/"

configure_logging(SERVICE_NAME, level=config("LOG_LEVEL", default="INFO"))
