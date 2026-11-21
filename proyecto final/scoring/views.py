import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .artifacts import ModelArtifactsError, load_config, load_metrics, missing_artifacts
from .scorer import mock_enabled, score_segments_detailed


def model_info(request):
    metrics = load_metrics()
    config = {}
    artifacts_error = ""
    try:
        config = load_config()
    except ModelArtifactsError as exc:
        artifacts_error = str(exc)

    return render(
        request,
        "model/info.html",
        {
            "metrics": metrics,
            "metrics_pretty": json.dumps(metrics, indent=2, ensure_ascii=False)
            if metrics
            else "",
            "config": config,
            "mock": mock_enabled(),
            "artifacts_error": artifacts_error,
            "missing_artifacts": missing_artifacts(),
        },
    )


@require_POST
def model_try(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido", "code": "invalid_json"}, status=400)

    text = (payload.get("text") or "").strip()
    if not text:
        return JsonResponse(
            {"error": "El texto es obligatorio", "code": "missing_text"}, status=400
        )
    if len(text) > 500:
        return JsonResponse(
            {"error": "El texto supera los 500 caracteres", "code": "text_too_long"},
            status=400,
        )

    try:
        result = score_segments_detailed([text])[0]
    except ModelArtifactsError as exc:
        return JsonResponse({"error": str(exc), "code": "model_unavailable"}, status=503)

    return JsonResponse(result)
