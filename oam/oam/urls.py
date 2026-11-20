"""
URL configuration for OAM project.
"""
from django.urls import path, include
from django.http import JsonResponse


def health(request):
    return JsonResponse({"status": "ok", "service": "oam"})


urlpatterns = [
    path("health", health),
    path("api/", include("oam.core.urls")),
]