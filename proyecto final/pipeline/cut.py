"""Recorte de clips y generación de miniaturas con ffmpeg."""

from pathlib import Path

from .audio import run_ffmpeg
from .errors import PipelineError


def cut_clip(src, start: float, end: float, out) -> Path:
    """Recorta `[start, end]` con recodificación (precisión de fotograma)."""
    start = float(start)
    end = float(end)
    if end <= start:
        raise PipelineError("El intervalo del clip no es válido.")

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{end - start:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(out),
        ]
    )
    return out


def make_thumbnail(src, at: float, out) -> Path:
    """Genera una miniatura JPG en el segundo `at`."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-ss",
            f"{float(at):.3f}",
            "-frames:v",
            "1",
            "-vf",
            "scale=480:-2",
            str(out),
        ]
    )
    return out
