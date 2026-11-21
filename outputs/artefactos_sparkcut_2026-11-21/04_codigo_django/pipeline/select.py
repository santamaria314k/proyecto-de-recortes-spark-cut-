"""Selección voraz de fragmentos por puntaje y solapamiento.

Contrato de `openspec/project.md`::

    select_clips(windows, scores, threshold=70, max_clips=10, max_overlap=0.30)
        -> list[ClipSpec]

`ClipSpec` es `{start, end, score, tier, text, explanation}`. El umbral es
estricto (un puntaje exactamente igual a 70 no es `high`) y, si ningún
fragmento lo supera, se devuelven hasta 3 con `tier='medium'`.
"""

from .errors import PipelineError

THRESHOLD = 70.0
MAX_CLIPS = 10
MAX_OVERLAP = 0.30
MEDIUM_CLIPS = 3


def _overlap_ratio(first: dict, second: dict) -> float:
    """Fracción del intervalo más corto que queda cubierta por el otro."""
    first_start, first_end = float(first["start"]), float(first["end"])
    second_start, second_end = float(second["start"]), float(second["end"])
    intersection = max(0.0, min(first_end, second_end) - max(first_start, second_start))
    shorter = min(first_end - first_start, second_end - second_start)
    if shorter <= 0:
        return 0.0
    return intersection / shorter


def _clip_spec(window: dict, score: float, tier: str) -> dict:
    return {
        "start": float(window["start"]),
        "end": float(window["end"]),
        "score": float(score),
        "tier": tier,
        "text": window.get("text", ""),
        "explanation": {},
    }


def select_clips(
    windows: list[dict],
    scores: list[float],
    threshold: float = THRESHOLD,
    max_clips: int = MAX_CLIPS,
    max_overlap: float = MAX_OVERLAP,
) -> list[dict]:
    """Selecciona como máximo `max_clips` ventanas sin solaparse más de `max_overlap`."""
    if len(windows) != len(scores):
        raise PipelineError("La cantidad de ventanas y de puntajes no coincide.")

    # Mayor puntaje primero; a igual puntaje, el inicio más temprano.
    order = sorted(
        range(len(windows)),
        key=lambda index: (-float(scores[index]), float(windows[index]["start"])),
    )

    def pick(candidates: list[int], limit: int, tier: str) -> list[dict]:
        chosen: list[int] = []
        for index in candidates:
            if any(
                _overlap_ratio(windows[index], windows[other]) > max_overlap
                for other in chosen
            ):
                continue
            chosen.append(index)
            if len(chosen) >= limit:
                break
        return [_clip_spec(windows[index], scores[index], tier) for index in chosen]

    high_candidates = [index for index in order if float(scores[index]) > threshold]
    high = pick(high_candidates, max_clips, "high")
    if high:
        return high

    # Respaldo: los mejores disponibles, sin solaparse, como «potencial medio».
    return pick(order, min(MEDIUM_CLIPS, max_clips), "medium")
