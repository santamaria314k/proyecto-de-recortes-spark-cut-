"""Transcripción del audio con faster-whisper (CPU, int8).

La transcripción conserva el texto original (idioma del video) y, cuando el
idioma no es inglés, añade `text_en` con la traducción al inglés para que el
modelo —entrenado en inglés— pueda puntuar el contenido. La traducción usa la
misma pasada de Whisper con `task="translate"`; no necesita servicios externos.
"""

import logging
import wave

from .errors import DependencyMissingError, PipelineError

logger = logging.getLogger(__name__)


class TranscriptionError(PipelineError):
    """El audio no produjo una transcripción utilizable."""


def _read_wav(audio_path):
    """Lee un WAV PCM de 16 bits y devuelve muestras float32 en [-1, 1].

    Se entregan las muestras ya decodificadas para no depender del decodificador
    de PyAV (`av.open`), cuya firma cambió entre versiones y rompía la
    transcripción real. `audio.extract_audio` ya normaliza a mono 16 kHz.
    """
    import numpy as np

    try:
        with wave.open(str(audio_path), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            frames = wav.readframes(wav.getnframes())
    except (OSError, wave.Error) as exc:
        raise TranscriptionError("No se pudo leer el audio del video.") from exc

    if sample_width != 2:
        raise TranscriptionError("El audio debe ser WAV PCM de 16 bits.")

    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples


def _collect(segments) -> list[dict]:
    """Convierte los segmentos de faster-whisper en dicts ordenados por `start`."""
    collected = []
    for segment in segments:
        text = (segment.text or "").strip()
        if not text:
            continue
        collected.append(
            {
                "start": round(float(segment.start), 2),
                "end": round(float(segment.end), 2),
                "text": text,
            }
        )
    collected.sort(key=lambda segment: segment["start"])
    return collected


def _english_for(segment: dict, translated: list[dict]) -> str:
    """Devuelve el texto inglés que cubre el tramo del segmento original.

    La pasada de traducción puede cortar los subtítulos en límites distintos, así
    que se unen los fragmentos que se solapan y, si no hay solape, se usa el más
    cercano en el tiempo para no dejar el segmento sin traducción.
    """
    overlapping = [
        item["text"]
        for item in translated
        if item["start"] < segment["end"] and item["end"] > segment["start"]
    ]
    if not overlapping:
        nearest = min(
            translated,
            key=lambda item: abs(item["start"] - segment["start"]),
        )
        overlapping = [nearest["text"]]
    return " ".join(" ".join(overlapping).split())


def _add_english(
    model, samples, collected: list[dict], language: str
) -> None:
    """Añade `text_en` a cada segmento; si la pasada falla, sigue sin traducir."""
    try:
        # Se fija el idioma detectado para no volver a detectarlo por ventana.
        segments, _ = model.transcribe(
            samples, task="translate", vad_filter=True, language=language
        )
        translated = _collect(segments)
    except Exception:  # la traducción no debe tumbar el pipeline
        logger.warning("No se pudo traducir la transcripción al inglés", exc_info=True)
        return

    if not translated:
        logger.warning("La pasada de traducción no devolvió texto; se puntúa el original")
        return

    for segment in collected:
        english = _english_for(segment, translated)
        if english:
            segment["text_en"] = english


def transcribe(audio_path, model_size: str = "small", translate: bool = True) -> dict:
    """Transcribe el audio y devuelve `{language, segments}`.

    Cada segmento es `{start, end, text}` en segundos y queda ordenado por
    `start`. Si el idioma detectado no es inglés se añade `text_en` con la
    traducción. El import de `faster_whisper` es diferido para que la suite de
    pruebas y `manage.py check` funcionen sin la dependencia instalada.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise DependencyMissingError(
            "faster-whisper no está instalado en el worker de procesamiento."
        ) from exc

    samples = _read_wav(audio_path)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(samples, vad_filter=True, language=None)

    collected = _collect(segments)
    if not collected:
        raise TranscriptionError("No se encontró voz en el audio del video.")

    language = (getattr(info, "language", None) or "es").lower()
    if translate and language != "en":
        _add_english(model, samples, collected, language)

    return {"language": language, "segments": collected}
