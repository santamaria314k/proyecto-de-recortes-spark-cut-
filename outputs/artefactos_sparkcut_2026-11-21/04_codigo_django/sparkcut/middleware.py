"""Middleware que traduce subidas demasiado grandes a 413."""

from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse
from django.shortcuts import render


class UploadTooLargeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except RequestDataTooBig:
            message = "El archivo supera el tamaño máximo permitido de 500 MB."
            if "application/json" in request.headers.get("Accept", ""):
                return JsonResponse(
                    {"error": message, "code": "file_too_large"}, status=413
                )
            return render(request, "413.html", status=413)
