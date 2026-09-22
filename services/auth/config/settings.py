"""Settings for the auth service. One file, values come from the environment."""

from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

from py_common.logging import configure_logging

BASE_DIR = Path(__file__).resolve().parent.parent
SERVICE_NAME = "auth"

SECRET_KEY = config("SECRET_KEY", default="dev-only-not-secret")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "accounts",
]

MIDDLEWARE = [
    "py_common.web.django.correlation_id_middleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES: dict[str, dict[str, object]] = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("AUTH_DB_NAME", default="auth_db"),
        "USER": config("AUTH_DB_USER", default="auth_user"),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("POSTGRES_HOST", default="postgres"),
        "PORT": config("POSTGRES_PORT", default=5432, cast=int),
        "CONN_MAX_AGE": 60,
    }
}

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

REST_FRAMEWORK: dict[str, object] = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": ["py_common.web.drf.GatewayAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["py_common.web.drf.IsAuthenticatedUser"],
    "DEFAULT_PAGINATION_CLASS": "py_common.web.drf.PagePagination",
    "EXCEPTION_HANDLER": "py_common.web.drf.exception_handler",
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS: dict[str, object] = {
    "TITLE": "Auth service",
    "VERSION": "0.1.0",
    "SCHEMA_PATH_PREFIX": "/api/auth",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "UserRoleEnum": "contracts.enums.UserRole",
    },
}

# JWT (RS256). Keys are files: mounted secrets in containers, throwaway pairs in tests.
JWT_PRIVATE_KEY_PATH = config("JWT_PRIVATE_KEY_PATH", default="/run/secrets/jwt_private.pem")
JWT_PUBLIC_KEY_PATH = config("JWT_PUBLIC_KEY_PATH", default="/run/secrets/jwt_public.pem")
JWT_ISSUER = "marketplace-auth"
SIMPLE_JWT: dict[str, object] = {
    "ALGORITHM": "RS256",
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config("ACCESS_TOKEN_LIFETIME_MINUTES", default=15, cast=int)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config("REFRESH_TOKEN_LIFETIME_DAYS", default=30, cast=int)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "sub",
    "ISSUER": JWT_ISSUER,
    # Keys are loaded lazily by accounts.tokens, never at import time.
    "SIGNING_KEY": None,
    "VERIFYING_KEY": "",
}

# One time passwords.
REDIS_URL = config("REDIS_URL", default="redis://redis:6379/0")
OTP_LENGTH = 6
OTP_TTL_SECONDS = 120
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = 60
OTP_MASTER_CODE = "000000"  # accepted only while DEBUG is on
PHONE_ALLOWED_REGIONS = config("PHONE_ALLOWED_REGIONS", default="UZ", cast=Csv())

SMS_BACKEND = config("SMS_BACKEND", default="console")
ESKIZ_EMAIL = config("ESKIZ_EMAIL", default="")
ESKIZ_PASSWORD = config("ESKIZ_PASSWORD", default="")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
STATIC_URL = "static/"

configure_logging(SERVICE_NAME, level=config("LOG_LEVEL", default="INFO"))
