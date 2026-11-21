"""Inspección y extracción de audio con ffmpeg/ffprobe.

Los comandos se ejecutan con `shell=False` y los errores se traducen a
`PipelineError` con mensajes legibles para la interfaz.
"""

import json
import subprocess
from pathlib import Path

from .errors import DependencyMissingError, PipelineError


class MediaError(PipelineError):
    """ffmpeg o ffprobe no pudieron procesar el archivo."""


class NoAudioError(MediaError):
    """El video no contiene una pista de audio."""


class NoVideoStreamError(MediaError):
    """El archivo no contiene una pista de video."""


def run_ffmpeg(cmd: list[str]) -> subprocess.CompletedProcess:
    """Ejecuta ffmpeg/ffprobe sin shell y traduce sus fallos."""
    try:
        return subprocess.run(
            cmd,
            shell=False,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise DependencyMissingError(
            "ffmpeg/ffprobe no está instalado en el servidor de procesamiento."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise MediaError("No se pudo procesar el video con ffmpeg.") from exc


def probe_duration(video_path) -> float:
    """Devuelve la duración del video en segundos."""
    result = run_ffmpeg(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video_path),
        ]
    )
    try:
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MediaError("No se pudo leer la duración del video.") from exc
    if duration <= 0:
        raise MediaError("El video tiene una duración inválida.")
    return duration


def has_audio(video_path) -> bool:
    """Indica si el archivo contiene al menos una pista de audio."""
    result = run_ffmpeg(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "json",
            str(video_path),
        ]
    )
    try:
        streams = json.loads(result.stdout or "{}").get("streams", [])
    except (TypeError, ValueError) as exc:
        raise MediaError("No se pudieron leer las pistas del video.") from exc
    return any(stream.get("codec_type") == "audio" for stream in streams)


def has_video(video_path) -> bool:
    """Indica si el archivo contiene al menos una pista de video."""
    result = run_ffmpeg(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "json",
            str(video_path),
        ]
    )
    try:
        streams = json.loads(result.stdout or "{}").get("streams", [])
    except (TypeError, ValueError) as exc:
        raise MediaError("No se pudieron leer las pistas del video.") from exc
    return any(stream.get("codec_type") == "video" for stream in streams)


def validate_video(video_path, max_duration_s: int = 1200) -> float:
    """Valida duración, pista de audio y pista de video."""
    duration = probe_duration(video_path)
    if duration > max_duration_s:
        raise MediaError(
            f"El video dura {duration:.0f} s y el máximo permitido es {max_duration_s} s."
        )
    if not has_audio(video_path):
        raise NoAudioError("El video no contiene una pista de audio.")
    if not has_video(video_path):
        raise NoVideoStreamError("El archivo no contiene una pista de video.")
    return duration


def extract_audio(video_path, audio_path) -> Path:
    """Extrae el audio a WAV mono 16 kHz, el formato que consume Whisper."""
    audio_path = Path(audio_path)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(audio_path),
        ]
    )
    return audio_path
