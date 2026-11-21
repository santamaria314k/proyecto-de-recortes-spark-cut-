"""Tarea de re-recorte de un clip con los nuevos límites del usuario."""

import tempfile
from pathlib import Path

from celery import shared_task
from django.conf import settings

from pipeline.cut import cut_clip, make_thumbnail
from pipeline.errors import PipelineError

from .models import Clip

MIN_CLIP_S = 3
MAX_CLIP_S = 90


def validate_range(start, end, duration_s=None):
    """Valida el intervalo pedido y devuelve `(error, code)` o `(None, None)`."""
    try:
        start = float(start)
        end = float(end)
    except (TypeError, ValueError):
        return "El intervalo debe incluir números para el inicio y el final.", "invalid_range"

    if start < 0:
        return "El inicio no puede ser negativo.", "invalid_range"
    if end <= start:
        return "El final debe ser mayor que el inicio.", "invalid_range"

    length = end - start
    if length < MIN_CLIP_S or length > MAX_CLIP_S:
        return (
            f"La duración del clip debe estar entre {MIN_CLIP_S} y {MAX_CLIP_S} segundos.",
            "invalid_duration",
        )

    if duration_s and end > float(duration_s) + 0.5:
        return (
            "El clip no puede terminar después del final del video.",
            "out_of_bounds",
        )
    return None, None


@shared_task(
    soft_time_limit=settings.PIPELINE_TIME_LIMIT_S,
    time_limit=settings.PIPELINE_TIME_LIMIT_S + 60,
)
def recut_clip(clip_id):
    """Regenera el archivo del clip con sus límites actuales."""
    try:
        clip = Clip.objects.select_related("video").get(pk=clip_id)
    except Clip.DoesNotExist:
        return

    video = clip.video
    if not video.file:
        Clip.objects.filter(pk=clip.pk).update(recut_status=Clip.RecutStatus.FAILED)
        return

    with tempfile.TemporaryDirectory(prefix="sparkcut-recut-") as temp:
        temp_dir = Path(temp)
        try:
            out = cut_clip(
                video.file.path,
                clip.start_time,
                clip.end_time,
                temp_dir / "clip.mp4",
            )
            thumb = make_thumbnail(
                video.file.path,
                clip.start_time,
                temp_dir / "thumb.jpg",
            )

            previous_file = clip.file
            previous_thumb = clip.thumbnail

            with Path(out).open("rb") as handle:
                clip.file.save(Path(out).name, handle, save=False)
            with Path(thumb).open("rb") as handle:
                clip.thumbnail.save(Path(thumb).name, handle, save=False)
            clip.recut_status = Clip.RecutStatus.READY
            clip.save(
                update_fields=["file", "thumbnail", "recut_status", "edited"]
            )

            # Los archivos anteriores se borran después de guardar los nuevos.
            if previous_file and previous_file.name != clip.file.name:
                previous_file.delete(save=False)
            if previous_thumb and previous_thumb.name != clip.thumbnail.name:
                previous_thumb.delete(save=False)

        except (PipelineError, OSError):
            Clip.objects.filter(pk=clip.pk).update(
                recut_status=Clip.RecutStatus.FAILED
            )
            raise
