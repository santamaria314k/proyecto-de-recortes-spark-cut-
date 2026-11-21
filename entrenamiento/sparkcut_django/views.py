from __future__ import annotations

import json
import math
from typing import Any

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .inference import get_scorer


MAX_SEGMENTS = 5000
MAX_TEXT_CHARS = 20000


def _windows(segments: list[dict[str, Any]], cfg: dict[str, Any], include_visual_context: bool = False) -> list[dict[str, Any]]:
    """Create overlapping 10–45 second transcript windows like the training pipeline."""
    target = float(cfg["window"]["target"])
    minimum = float(cfg["window"]["min"])
    maximum = float(cfg["window"]["max"])
    hop = float(cfg["window"]["hop"])
    min_words = 12
    min_lexdiv = 0.30
    windows = []
    i = 0
    while i < len(segments):
        start = segments[i]["start"]
        j = i
        while (j + 1 < len(segments)
               and segments[j]["end"] - start < target
               and segments[j + 1]["end"] - start <= maximum):
            j += 1
        end = segments[j]["end"]
        text = " ".join(row["text"] for row in segments[i:j + 1]).strip()
        visual = list(dict.fromkeys(
            row["visual_context"] for row in segments[i:j + 1]
            if include_visual_context and row.get("visual_context")
        ))
        if visual:
            text = "Visual events: " + " | ".join(visual[:20]) + " Transcript: " + text
        words = text.lower().split()
        if (minimum <= end - start <= maximum and len(words) >= min_words
                and len(set(words)) / len(words) >= min_lexdiv):
            windows.append({"start": start, "end": end, "text": text})
        next_i = i + 1
        while next_i < len(segments) and segments[next_i]["start"] < start + hop:
            next_i += 1
        i = next_i
    return windows


def _relative_ranks(values: list[float]) -> list[float]:
    if len(values) == 1:
        return [50.0]
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    for rank, index in enumerate(order):
        ranks[index] = 100.0 * rank / (len(order) - 1)
    return ranks


@require_GET
def health(request):
    return JsonResponse({"status": "ok", "service": "sparkcut"})


@csrf_exempt
@require_POST
def score_video(request):
    """POST timed transcript segments and receive ranked candidate short clips."""
    try:
        body = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Request body must be valid JSON."}, status=400)
    if not isinstance(body, dict) or not isinstance(body.get("segments"), list):
        return JsonResponse({"error": "Expected an object with a 'segments' array."}, status=400)
    if not body["segments"] or len(body["segments"]) > MAX_SEGMENTS:
        return JsonResponse({"error": f"segments must contain 1–{MAX_SEGMENTS} items."}, status=400)
    limit = body.get("max_clips", 10)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        return JsonResponse({"error": "max_clips must be an integer from 1 to 100."}, status=400)

    segments = []
    try:
        for item in body["segments"]:
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                raise ValueError("Each segment needs string text, start, and end fields.")
            text = item["text"].strip()
            visual_context = item.get("visual_context", "")
            start, end = float(item["start"]), float(item["end"])
            if not text or len(text) > MAX_TEXT_CHARS:
                raise ValueError(f"Segment text must contain 1–{MAX_TEXT_CHARS} characters.")
            if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
                raise ValueError("Segment times must be finite and satisfy 0 <= start < end.")
            if not isinstance(visual_context, str) or len(visual_context) > 5000:
                raise ValueError("visual_context must be a string of at most 5000 characters.")
            segments.append({"start": start, "end": end, "text": text,
                             "visual_context": visual_context.strip()})
        segments.sort(key=lambda row: (row["start"], row["end"]))
        for previous, current in zip(segments, segments[1:]):
            if current["start"] < previous["start"]:
                raise ValueError("Segments must be ordered by start time.")
    except (KeyError, TypeError, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    try:
        scorer = get_scorer()
        uses_visual_context = bool(scorer.config.get("uses_visual_context", False))
        windows = _windows(segments, scorer.config, include_visual_context=uses_visual_context)
        if not windows:
            return JsonResponse({"clips": [], "message": "No transcript windows met the minimum length and text requirements."})
        predictions = scorer.score_texts([window["text"] for window in windows])
        model_ranks = _relative_ranks([prediction["score"] for prediction in predictions])
        position_ranks = None
        context_ranks = None
        blend = scorer.config.get("rank_blend")
        if scorer.context_ranker is not None:
            context_ranks = scorer.score_contextual_ranks(
                [window["text"] for window in windows],
                [prediction["score"] for prediction in predictions],
            )
            combined = [100.0 * score for score in context_ranks["combined"]]
        elif blend and scorer.position_ranker is not None:
            position_ranks = _relative_ranks(scorer.score_positions(windows))
            combined = [float(blend["rnn"]) * model_ranks[i]
                        + float(blend["position"]) * position_ranks[i]
                        for i in range(len(windows))]
        else:
            combined = model_ranks
        relative_score = [round(x, 1) for x in _relative_ranks(combined)]
        results = []
        for i, (window, prediction) in enumerate(zip(windows, predictions)):
            result = {**window, "model_score": prediction["score"],
                      "score": relative_score[i], **{k: v for k, v in prediction.items() if k != "score"}}
            if position_ranks is not None:
                result["text_rank"] = round(model_ranks[i], 1)
                result["position_rank"] = round(position_ranks[i], 1)
            if context_ranks is not None:
                result["text_rank"] = round(model_ranks[i], 1)
                result["tfidf_rank"] = round(100 * context_ranks["tfidf"][i], 1)
                result["novelty_rank"] = round(100 * context_ranks["novelty_next"][i], 1)
            results.append(result)
        results.sort(key=lambda row: row["score"], reverse=True)
        return JsonResponse({
            "model_version": scorer.config["version"],
            "uses_teacher_labels": scorer.config.get("uses_teacher", False),
            "training_source": scorer.config.get("training_source"),
            "target_is_segment_viral_label": scorer.config.get("target_is_segment_viral_label", False),
            "production_ready": scorer.config.get("production_ready", False),
            "score_is_probability": False,
            "score_basis": "relative_rank_within_video",
            "rank_blend": scorer.config.get("rank_blend", {"rnn": 1.0, "position": 0.0}),
            "context_rank_blend": scorer.config.get("context_rank_blend"),
            "predicts_future_virality": False,
            "uses_visual_context": uses_visual_context,
            "clips": results[:limit],
        })
    except (OSError, RuntimeError, ValueError) as exc:
        return JsonResponse({"error": "SparkCut model could not score this request.", "detail": str(exc)}, status=503)
