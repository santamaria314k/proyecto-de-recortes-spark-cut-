"""Puntaje de fragmentos con el modelo real o con el simulador de desarrollo.

Mantiene la firma pública descrita en openspec/project.md:
- score_segments(texts) -> list[float]
- score_segments_detailed(texts) -> list[dict]

Con `MOCK_SCORER=1` se usa un puntaje simulado determinista (desarrollo y
pruebas). En el despliegue (`MOCK_SCORER=0`) se cargan los artefactos de
`ml_artifacts/`; si falta alguno, el error indica cuál.
"""

import hashlib

from django.conf import settings

DIMENSIONS = ("hook", "emotion", "surprise", "conflict", "story")


def mock_enabled() -> bool:
    return bool(getattr(settings, "MOCK_SCORER", False))


def _mock_score(text: str) -> float:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    value = int.from_bytes(digest[:2], "big") % 901 + 100
    # El contrato de `score_segments` fija el rango 10.0–100.0.
    return round(min(100.0, 10 + value / 10), 1)


def score_segments(texts: list[str]) -> list[float]:
    if not texts:
        return []
    if mock_enabled():
        return [_mock_score(text) for text in texts]

    from .real import predict

    return predict(list(texts))


def score_segments_detailed(texts: list[str]) -> list[dict]:
    if not texts:
        return []
    if mock_enabled():
        return [{
            "score": _mock_score(text),
            "dims": {dim: round(min(100.0, _mock_score(text) + index), 1)
                     for index, dim in enumerate(DIMENSIONS)},
            "top_emotions": [("neutral", 1.0)],
        } for text in texts]

    from .real import predict_detailed

    return predict_detailed(list(texts))


def score_segments_contextual_detailed(texts: list[str]) -> list[dict]:
    """Puntúa una lista completa de ventanas con el ranker v6 contextual."""
    if not texts:
        return []
    if mock_enabled():
        return score_segments_detailed(texts)

    from .real import predict_contextual

    return predict_contextual(list(texts))
