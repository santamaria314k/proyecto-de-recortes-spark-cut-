"""Carga de los artefactos que entrega el entrenamiento (`ml_artifacts/`).

Contrato en `openspec/project.md`: pesos `model_*.pt`, `tokenizer.model`,
`config.json`, `metrics.json` y `golden_tests.json`. Si falta un archivo, el
error indica cuál falta.
"""

import json
from pathlib import Path

from django.conf import settings


class ModelArtifactsError(Exception):
    """Faltan artefactos del modelo o no son legibles."""


REQUIRED_FILES = (
    "config.json",
    "tokenizer.model",
    "metrics.json",
    "golden_tests.json",
)


def artifacts_dir() -> Path:
    return Path(getattr(settings, "ML_ARTIFACTS_DIR", "ml_artifacts"))


def model_files(config: dict) -> list[Path]:
    directory = artifacts_dir()
    declared = config.get("model_files") if isinstance(config, dict) else None
    if declared:
        return [directory / name for name in declared]
    return sorted(directory.glob("model_*.pt"))


def missing_artifacts(directory: Path | None = None) -> list[str]:
    directory = Path(directory or artifacts_dir())
    missing = [name for name in REQUIRED_FILES if not (directory / name).is_file()]

    weights = sorted(directory.glob("model_*.pt"))
    if not weights:
        missing.append("model_0.pt (y el resto del ensamble)")
    return missing


def _read_json(name: str):
    path = artifacts_dir() / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ModelArtifactsError(
            f"Falta el artefacto {name} en {artifacts_dir()}."
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelArtifactsError(
            f"No se pudo leer el artefacto {name}: {exc}"
        ) from exc


def load_config() -> dict:
    missing = missing_artifacts()
    if missing:
        raise ModelArtifactsError(
            "Faltan artefactos del modelo: " + ", ".join(missing)
        )

    config = _read_json("config.json")
    if not isinstance(config, dict):
        raise ModelArtifactsError("config.json no tiene el formato esperado.")

    context_file = config.get("context_ranker_file")
    if context_file and not (artifacts_dir() / context_file).is_file():
        raise ModelArtifactsError(
            f"Falta el artefacto contextual {context_file} en {artifacts_dir()}."
        )

    weights = model_files(config)
    if not weights:
        raise ModelArtifactsError(
            "config.json no declara modelos y no hay archivos model_*.pt."
        )
    missing_weights = [path.name for path in weights if not path.is_file()]
    if missing_weights:
        raise ModelArtifactsError(
            "Faltan pesos del modelo: " + ", ".join(missing_weights)
        )
    return config


def load_metrics() -> dict:
    try:
        metrics = _read_json("metrics.json")
    except ModelArtifactsError:
        return {}
    return metrics if isinstance(metrics, dict) else {}


def load_golden_tests() -> dict:
    try:
        golden = _read_json("golden_tests.json")
    except ModelArtifactsError:
        return {}
    return golden if isinstance(golden, dict) else {}
