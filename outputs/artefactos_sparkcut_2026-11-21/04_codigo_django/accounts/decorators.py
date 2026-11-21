"""Utilidades de autenticación para endpoints JSON."""

from functools import wraps

from django.http import JsonResponse


def login_required_json(view):
    """Devuelve 403 JSON en vez de redirigir al login (spec de autenticación)."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {
                    "error": "Necesitas iniciar sesión para acceder a este recurso.",
                    "code": "not_authenticated",
                },
                status=403,
            )
        return view(request, *args, **kwargs)

    return wrapper
