"""Settings for the order service. One file, values come from the environment."""

from pathlib import Path

from decouple import config

from py_common.logging import configure_logging

BASE_DIR = Path(__file__).resolve().parent.parent
SERVICE_NAME = "order"

SECRET_KEY = config("SECRET_KEY", default="dev-only-not-secret")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="*").split(",")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "messaging",
    "orders",
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
        "NAME": config("ORDER_DB_NAME", default="order_db"),
        "USER": config("ORDER_DB_USER", default="order_user"),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("POSTGRES_HOST", default="postgres"),
        "PORT": config("POSTGRES_PORT", default=5432, cast=int),
        "CONN_MAX_AGE": 60,
    }
}

REST_FRAMEWORK: dict[str, object] = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": ["py_common.web.drf.GatewayAuthentication"],
    # Every order route needs a signed-in user; the gateway already demands a token.
    "DEFAULT_PERMISSION_CLASSES": ["py_common.web.drf.IsAuthenticatedUser"],
    "DEFAULT_PAGINATION_CLASS": "py_common.web.drf.PagePagination",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "py_common.web.drf.exception_handler",
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS: dict[str, object] = {
    "TITLE": "Order service",
    "VERSION": "0.1.0",
    "SCHEMA_PATH_PREFIX": "/api/orders",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "OrderStatusEnum": "orders.models.ORDER_STATUS_CHOICES",
        "SubOrderStatusEnum": "orders.models.SUB_ORDER_STATUS_CHOICES",
        "SubOrderTargetStatusEnum": "orders.serializers.SELLER_TARGETS",
    },
}

# Redis: checkout idempotency keys.
REDIS_URL = config("REDIS_URL", default="redis://redis:6379/0")
IDEMPOTENCY_TTL_SECONDS = config("IDEMPOTENCY_TTL_SECONDS", default=24 * 3600, cast=int)
# Upper bound of one checkout; a crashed request frees its key after this.
IDEMPOTENCY_LOCK_SECONDS = config("IDEMPOTENCY_LOCK_SECONDS", default=60, cast=int)

# Internal services, reached over the private network only.
CART_INTERNAL_URL = config("CART_INTERNAL_URL", default="http://cart:8000")
CATALOG_INTERNAL_URL = config("CATALOG_INTERNAL_URL", default="http://catalog:8000")
INTERNAL_HTTP_TIMEOUT_SECONDS = config("INTERNAL_HTTP_TIMEOUT_SECONDS", default=3.0, cast=float)

# RabbitMQ: the outbox relay publishes to it, the consumer reads order.q from it.
RABBITMQ_URL = config("RABBITMQ_URL", default="amqp://rabbitmq:5672/")
OUTBOX_RELAY_INTERVAL_SECONDS = config("OUTBOX_RELAY_INTERVAL_SECONDS", default=1.0, cast=float)
OUTBOX_RELAY_BATCH_SIZE = config("OUTBOX_RELAY_BATCH_SIZE", default=100, cast=int)

# Celery: Redis db 1 as the broker, results are not stored. The broker is shared with the
# catalog worker, so order tasks travel on their own queue.
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://redis:6379/1")
CELERY_TASK_DEFAULT_QUEUE = "order"
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TIMEZONE = "UTC"
# Overdue RESERVED orders become EXPIRED (and release their stock) on this schedule.
ORDER_EXPIRY_INTERVAL_SECONDS = config("ORDER_EXPIRY_INTERVAL_SECONDS", default=30.0, cast=float)
CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {
    "expire-overdue-orders": {
        "task": "orders.expire_overdue_orders",
        "schedule": ORDER_EXPIRY_INTERVAL_SECONDS,
        # A run that waited longer than one interval is superseded by the next one.
        "options": {"expires": ORDER_EXPIRY_INTERVAL_SECONDS},
    }
}

# The mock payment endpoint exists only when this is on AND DEBUG is on.
PAYMENT_MOCK_ENABLED = config("PAYMENT_MOCK_ENABLED", default=False, cast=bool)

# /metrics of the order consumer (no web server of its own); 0 turns it off.
CONSUMER_METRICS_PORT = config("CONSUMER_METRICS_PORT", default=9100, cast=int)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
STATIC_URL = "static/"

configure_logging(SERVICE_NAME, level=config("LOG_LEVEL", default="INFO"))
