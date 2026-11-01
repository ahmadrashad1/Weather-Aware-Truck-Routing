from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.urls import include, path


def health(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok", "version": settings.APP_VERSION})


urlpatterns = [
    path("api/v1/health", health),
    path("api/v1/", include("routing.api.urls")),
]
