"""Vistas base y manejo de errores HTTP en español."""

from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render

JSON_PATHS = ("/status/", "/trim/", "/restore/", "/modelo/probar/")


def home(request):
    return render(request, "home.html")


def healthz(request):
    return JsonResponse({"status": "ok"})


def readyz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


def _wants_json(request) -> bool:
    accept = request.headers.get("Accept", "")
    return "application/json" in accept or request.path.endswith(JSON_PATHS)


def _error(request, status, message, code, template):
    if _wants_json(request):
        return JsonResponse({"error": message, "code": code}, status=status)
    return render(request, template, {"message": message}, status=status)


def handler400(request, exception=None):
    return _error(
        request,
        400,
        "La solicitud no es válida. Revisa los datos e inténtalo de nuevo.",
        "bad_request",
        "400.html",
    )


def handler403(request, exception=None):
    return _error(
        request,
        403,
        "No tienes permiso para acceder a este recurso.",
        "forbidden",
        "403.html",
    )


def handler404(request, exception=None):
    return _error(
        request,
        404,
        "El recurso no existe o no tienes acceso a él.",
        "not_found",
        "404.html",
    )


def handler500(request):
    return _error(
        request,
        500,
        "Ocurrió un error inesperado. Inténtalo más tarde.",
        "server_error",
        "500.html",
    )
