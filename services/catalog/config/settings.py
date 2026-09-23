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
    "django_filters",
    "mptt",
    "messaging",
    "sellers",
    "products",
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
    "DEFAULT_AUTHENTICATION_CLASSES": ["py_common.web.drf.GatewayAuthentication"],
    # Closed by default: public views opt out explicitly.
    "DEFAULT_PERMISSION_CLASSES": ["py_common.web.drf.IsAuthenticatedUser"],
    "DEFAULT_PAGINATION_CLASS": "py_common.web.drf.PagePagination",
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "py_common.web.drf.exception_handler",
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS: dict[str, object] = {
    "TITLE": "Catalog service",
    "VERSION": "0.1.0",
    "SCHEMA_PATH_PREFIX": "/api/catalog",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "ProductStatusEnum": "products.models.PRODUCT_STATUS_CHOICES",
        "ImageStatusEnum": "products.models.ImageStatus",
        "ImageContentTypeEnum": "products.storage.IMAGE_CONTENT_TYPE_CHOICES",
    },
}

# Object storage. S3_ENDPOINT is what the services use inside the network,
# S3_PUBLIC_ENDPOINT is what browsers reach: presigned upload URLs and public
# image URLs are built for it.
S3_ENDPOINT = config("S3_ENDPOINT", default="http://minio:9000")
S3_PUBLIC_ENDPOINT = config("S3_PUBLIC_ENDPOINT", default="http://minio.localhost")
S3_ACCESS_KEY = config("S3_ACCESS_KEY", default="")
S3_SECRET_KEY = config("S3_SECRET_KEY", default="")
S3_BUCKET = config("S3_BUCKET", default="marketplace")
S3_REGION = config("S3_REGION", default="us-east-1")
IMAGE_MAX_UPLOAD_BYTES = config("IMAGE_MAX_UPLOAD_BYTES", default=10 * 1024 * 1024, cast=int)
IMAGE_UPLOAD_URL_TTL_SECONDS = config("IMAGE_UPLOAD_URL_TTL_SECONDS", default=600, cast=int)

# Celery: Redis db 1 as the broker, results are not stored.
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://redis:6379/1")
CELERY_TASK_ALWAYS_EAGER = config("CELERY_TASK_ALWAYS_EAGER", default=False, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TIMEZONE = "UTC"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
STATIC_URL = "static/"

configure_logging(SERVICE_NAME, level=config("LOG_LEVEL", default="INFO"))
