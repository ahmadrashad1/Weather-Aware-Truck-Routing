import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_list(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


DEBUG = os.environ.get("DJANGO_DEBUG", "").lower() in {"1", "true", "yes"}

# Production must not start half-configured, with a known secret or a per-process cache.
if not DEBUG:
    for required in ("DJANGO_SECRET_KEY", "ALLOWED_HOSTS", "TOMTOM_API_KEY"):
        if not os.environ.get(required):
            raise ImproperlyConfigured(f"{required} must be set unless DJANGO_DEBUG is true")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or "insecure-dev-key"  # The default is DEBUG-only.

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS") or ["*"]
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "routing",
]

MIDDLEWARE = [
    "django.middleware.gzip.GZipMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES: dict[str, dict[str, str]] = {}

REDIS_URL = os.environ.get("REDIS_URL", "")
CACHES = (
    {
        "default": {
            "BACKEND": "config.cache.ResilientRedisCache",
            "LOCATION": REDIS_URL,
            # Fail fast if Redis is down, so a request falls back to the provider quickly.
            "OPTIONS": {"socket_connect_timeout": 1, "socket_timeout": 2},
        }
    }
    if REDIS_URL
    else {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            # This cache belongs to one process, so it suits the single worker the app runs. The
            # default of 300 entries is less than one long trip's weather cells, and this limit
            # keeps it to about 100 MB on a small server.
            "OPTIONS": {"MAX_ENTRIES": 5_000},
        }
    }
)

TOMTOM_API_KEY = os.environ.get("TOMTOM_API_KEY", "")
OPEN_METEO_API_KEY = os.environ.get("OPEN_METEO_API_KEY", "")
APP_VERSION = os.environ.get("APP_VERSION", "dev")

# How many trusted proxies sit in front of the app. Forwarded headers can be forged, so with 0 they
# are ignored and the connection's own address identifies the client. Behind a proxy, set this or
# all users share one rate limit. Too high, and a forged header can dodge the limit.
NUM_PROXIES = int(os.environ.get("NUM_PROXIES") or 0)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if NUM_PROXIES else None

SECURE_SSL_REDIRECT = (
    not DEBUG and os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "true").lower() != "false"
)
# A load balancer's health check usually arrives over plain HTTP.
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health$"]
SECURE_HSTS_SECONDS = 0 if DEBUG else 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
# HSTS preload is a permanent browser-list commitment for a domain, which is the owner's decision.
SILENCED_SYSTEM_CHECKS = ["security.W021"]

REST_FRAMEWORK = {
    "NUM_PROXIES": NUM_PROXIES,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "routing.api.errors.exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # These protect the provider quotas, which are shared by every user of the app.
    "DEFAULT_THROTTLE_RATES": {
        "trip_plan": "30/hour",
        "heatmap": "30/hour",
        "geocode": "120/minute",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Weather-Aware Truck Routing API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "ENUM_NAME_OVERRIDES": {
        "RiskEnum": "routing.api.serializers.RISK_CODES",
        "RiskOrUnknownEnum": "routing.api.serializers.RISK_OR_UNKNOWN_CODES",
    },
}

USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
