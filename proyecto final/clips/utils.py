"""Limpieza de archivos del almacén de medios.

El borrado en cascada de la base de datos no elimina archivos, así que la
limpieza se hace explícitamente (spec de clips y de gestión de videos).
"""

import logging

logger = logging.getLogger(__name__)


def delete_clip_files(clip) -> None:
    """Elimina el mp4 y la miniatura de un clip, sin tocar la base de datos."""
    for field in (clip.file, clip.thumbnail):
        if not field:
            continue
        try:
            field.delete(save=False)
        except Exception:  # la limpieza no debe impedir el borrado del registro
            logger.warning("No se pudo borrar el archivo del clip %s", clip.pk)


def delete_video_files(video) -> None:
    """Elimina el video original y los archivos de todos sus clips."""
    for clip in video.clips.all():
        delete_clip_files(clip)
    if video.file:
        try:
            video.file.delete(save=False)
        except Exception:
            logger.warning("No se pudo borrar el archivo del video %s", video.pk)
