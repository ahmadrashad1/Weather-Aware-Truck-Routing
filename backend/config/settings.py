import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_list(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


DEBUG = os.environ.get("DJANGO_DEBUG", "").lower() in {"1", "true", "yes"}

# Dev-only fallback so tests and local runs work without configuration; production must set it.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or (
    "insecure-dev-key" if DEBUG else "insecure-test-key-not-for-production"
)

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS") or (
    ["*"] if DEBUG else ["localhost", "127.0.0.1", "testserver"]
)
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "routing",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES: dict[str, dict[str, str]] = {}

REDIS_URL = os.environ.get("REDIS_URL", "")
CACHES = (
    {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}
    if REDIS_URL
    else {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)

TOMTOM_API_KEY = os.environ.get("TOMTOM_API_KEY", "")
OPEN_METEO_API_KEY = os.environ.get("OPEN_METEO_API_KEY", "")

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
