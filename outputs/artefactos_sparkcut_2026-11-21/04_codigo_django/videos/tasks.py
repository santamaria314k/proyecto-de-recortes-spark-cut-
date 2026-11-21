"""Tarea Celery que ejecuta el pipeline real de SparkCut."""

import logging
import tempfile
from pathlib import Path

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.core.files import File

from clips.models import Clip
from pipeline import audio, download
from pipeline.audio import validate_video
from pipeline.cut import cut_clip, make_thumbnail
from pipeline.errors import PipelineError
from pipeline.select import select_clips
from pipeline.transcribe import transcribe
from pipeline.windows import build_windows
from scoring.scorer import (
    score_segments,
    score_segments_contextual_detailed,
    score_segments_detailed,
)

from .models import Transcript, Video

logger = logging.getLogger(__name__)

TIME_LIMIT_S = settings.PIPELINE_TIME_LIMIT_S


class VideoDeleted(Exception):
    """El dueño eliminó el video mientras la tarea seguía en curso."""


def _update_video(video: Video, **fields) -> None:
    """Actualiza solo si la fila existe; si se borró, aborta la tarea."""
    updated = Video.objects.filter(pk=video.pk).update(**fields)
    if not updated:
        raise VideoDeleted
    for field, value in fields.items():
        setattr(video, field, value)


def _model_text(window: dict) -> str:
    """Texto que consume el modelo: la traducción al inglés si existe."""
    return window.get("text_en") or window.get("text") or ""


def _score_candidates(texts: list[str]) -> tuple[list[float], list[dict]]:
    """Usa el ranker contextual en producción y conserva el contrato de tests."""
    if settings.MOCK_SCORER:
        scores = score_segments(texts)
        return scores, score_segments_detailed(texts)
    details = score_segments_contextual_detailed(texts)
    return [item["score"] for item in details], details


def _set_phase(video: Video, status: str, progress: int) -> None:
    _update_video(video, status=status, progress=progress)


def _fail(video: Video, message: str) -> None:
    Video.objects.filter(pk=video.pk).update(
        status=Video.Status.FAILED, error=message
    )


def _friendly_message(exc: Exception) -> str:
    if isinstance(exc, PipelineError):
        return str(exc)
    return "Ocurrió un error inesperado al procesar el video."


def _resolve_source(video: Video, temp_dir: Path) -> Path:
    if video.source_type == Video.SourceType.URL:
        _set_phase(video, Video.Status.DOWNLOADING, 10)
        download.resolve_and_validate(video.source_url)

        # Si yt-dlp anuncia la duración, se rechaza antes de descargar (RF-06).
        duration = download.probe_duration(video.source_url)
        if duration and duration > settings.MAX_VIDEO_DURATION_S:
            raise PipelineError(
                f"El enlace dura {duration:.0f} s y el máximo permitido es "
                f"{settings.MAX_VIDEO_DURATION_S} s. Sube un video más corto."
            )
        return download.download(video.source_url, temp_dir / "download")

    if not video.file:
        raise PipelineError("El video no tiene un archivo asociado.")
    return Path(video.file.path)


def _save_clips(video, prepared, details, sink) -> None:
    for (spec, clip_path, thumb_path), detail in zip(prepared, details):
        clip = Clip.objects.create(
            video=video,
            start_time=spec["start"],
            end_time=spec["end"],
            orig_start_time=spec["start"],
            orig_end_time=spec["end"],
            score=spec["score"],
            tier=spec["tier"],
            text=spec["text"],
            explanation=detail or {},
            edited=False,
        )
        sink.append(clip)

        with Path(clip_path).open("rb") as handle:
            clip.file.save(Path(clip_path).name, File(handle), save=False)
        with Path(thumb_path).open("rb") as handle:
            clip.thumbnail.save(Path(thumb_path).name, File(handle), save=True)


def _cleanup_clips(clips) -> None:
    for clip in clips:
        for field in (clip.file, clip.thumbnail):
            if not field:
                continue
            try:
                field.delete(save=False)
            except Exception:  # la limpieza no debe ocultar el error original
                logger.warning("No se pudo borrar el archivo del clip %s", clip.pk)
        clip.delete()


@shared_task(
    soft_time_limit=TIME_LIMIT_S,
    time_limit=TIME_LIMIT_S + 60,
)
def process_video(video_id):
    """Ejecuta el pipeline completo para un `Video` y deja su estado final."""
    try:
        video = Video.objects.get(pk=video_id)
    except Video.DoesNotExist:
        return

    created_clips: list[Clip] = []

    try:
        _update_video(video, error="")

        with tempfile.TemporaryDirectory(prefix="sparkcut-") as temp:
            temp_dir = Path(temp)

            source = _resolve_source(video, temp_dir)
            duration = validate_video(
                source, max_duration_s=settings.MAX_VIDEO_DURATION_S
            )
            _update_video(video, duration_s=int(round(duration)))

            _set_phase(video, Video.Status.TRANSCRIBING, 40)
            audio_path = audio.extract_audio(source, temp_dir / "audio.wav")
            transcription = transcribe(
                audio_path, model_size=settings.WHISPER_MODEL
            )

            Transcript.objects.update_or_create(
                video=video,
                defaults={
                    "language": transcription["language"],
                    "segments": transcription["segments"],
                },
            )

            candidates = build_windows(transcription["segments"])
            if not candidates:
                raise PipelineError(
                    "No hay voz suficiente para generar fragmentos de al menos 10 segundos."
                )

            _set_phase(video, Video.Status.SCORING, 70)
            # El modelo está entrenado en inglés: se puntúa `text_en` cuando la
            # traducción existe y se conserva el texto original para mostrar.
            model_texts = [_model_text(window) for window in candidates]
            # v6 aprende el orden relativo dentro del video: la RNN aporta la
            # señal base y el ranker contextual usa el conjunto completo de
            # ventanas para medir cambio textual y relevancia.
            scores, scored = _score_candidates(model_texts)
            specs = select_clips(candidates, scores)
            if not specs:
                raise PipelineError(
                    "No se pudieron seleccionar fragmentos para este video."
                )

            _set_phase(video, Video.Status.CLIPPING, 90)
            prepared = []
            for index, spec in enumerate(specs):
                clip_path = cut_clip(
                    source,
                    spec["start"],
                    spec["end"],
                    temp_dir / f"clip_{index}.mp4",
                )
                thumb_path = make_thumbnail(
                    source,
                    spec["start"],
                    temp_dir / f"clip_{index}.jpg",
                )
                prepared.append((spec, clip_path, thumb_path))

            detail_by_bounds = {
                (float(candidate["start"]), float(candidate["end"])): detail
                for candidate, detail in zip(candidates, scored)
            }
            details = [detail_by_bounds.get(
                (float(spec["start"]), float(spec["end"])),
                {"score": spec["score"]},
            ) for spec in specs]
            if not Video.objects.filter(pk=video.pk).exists():
                raise VideoDeleted
            _save_clips(video, prepared, details, created_clips)

            _set_phase(video, Video.Status.DONE, 100)

    except VideoDeleted:
        logger.info("El video %s fue eliminado durante el procesamiento", video_id)
        _cleanup_clips(created_clips)
        return
    except SoftTimeLimitExceeded:
        logger.exception("El pipeline del video %s superó el tiempo límite", video_id)
        _cleanup_clips(created_clips)
        _fail(video, "El procesamiento superó el tiempo límite configurado.")
        raise
    except Exception as exc:
        logger.exception("Falló el pipeline del video %s", video_id)
        _cleanup_clips(created_clips)
        _fail(video, _friendly_message(exc))
        raise
