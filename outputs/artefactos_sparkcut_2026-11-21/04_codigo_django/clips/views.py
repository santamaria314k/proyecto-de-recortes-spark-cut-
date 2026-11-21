"""Panel y edición de clips: media con Range, tijera, estado y restauración."""

import json
import os
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from accounts.decorators import login_required_json

from .models import Clip
from .tasks import recut_clip, validate_range
from .utils import delete_clip_files

RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
CHUNK_SIZE = 64 * 1024


def _get_clip(request, pk):
    return get_object_or_404(Clip, pk=pk, video__user=request.user)


def _iter_file(handle, start: int, length: int):
    handle.seek(start)
    remaining = length
    while remaining > 0:
        chunk = handle.read(min(CHUNK_SIZE, remaining))
        if not chunk:
            break
        remaining -= len(chunk)
        yield chunk


def _range_response(request, path, content_type="video/mp4", attachment=None):
    """Responde 200 sin Range, 206 con Range válido y 416 si es inválido."""
    size = os.path.getsize(path)
    range_header = request.headers.get("Range", "").strip()

    if not range_header:
        response = FileResponse(open(path, "rb"), content_type=content_type)
        response["Accept-Ranges"] = "bytes"
        if attachment:
            response["Content-Disposition"] = f'attachment; filename="{attachment}"'
        return response

    match = RANGE_RE.match(range_header)
    if not match:
        return _range_not_satisfiable(size)

    raw_start, raw_end = match.groups()
    if raw_start:
        start = int(raw_start)
        end = int(raw_end) if raw_end else size - 1
    else:
        # Sufijo: bytes=-N significa los últimos N bytes.
        if not raw_end or int(raw_end) == 0:
            return _range_not_satisfiable(size)
        start = max(0, size - int(raw_end))
        end = size - 1

    if start >= size or end < start:
        return _range_not_satisfiable(size)
    end = min(end, size - 1)
    length = end - start + 1

    handle = open(path, "rb")
    response = StreamingHttpResponse(
        _iter_file(handle, start, length), content_type=content_type
    )
    response["Accept-Ranges"] = "bytes"
    response["Content-Range"] = f"bytes {start}-{end}/{size}"
    response["Content-Length"] = str(length)
    response.status_code = 206
    if attachment:
        response["Content-Disposition"] = f'attachment; filename="{attachment}"'
    return response


def _range_not_satisfiable(size):
    response = HttpResponse(status=416)
    response["Content-Range"] = f"bytes */{size}"
    response["Accept-Ranges"] = "bytes"
    return response


@login_required
def clip_media(request, pk):
    clip = _get_clip(request, pk)
    if not clip.file:
        raise Http404("El clip no tiene archivo.")
    return _range_response(request, clip.file.path)


@login_required
def clip_download(request, pk):
    clip = _get_clip(request, pk)
    if not clip.file:
        raise Http404("El clip no tiene archivo.")
    return _range_response(
        request,
        clip.file.path,
        attachment=f"clip-{clip.pk}.mp4",
    )


def _trim_error(message, code, status=400):
    return JsonResponse({"error": message, "code": code}, status=status)


@login_required_json
@require_POST
def clip_trim(request, pk):
    clip = _get_clip(request, pk)

    if clip.recut_status == Clip.RecutStatus.PROCESSING:
        return _trim_error(
            "Ya hay un re-recorte en curso para este clip.",
            "recut_in_progress",
            status=409,
        )

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return _trim_error("JSON inválido", "invalid_json")
    if not isinstance(payload, dict):
        return _trim_error("JSON inválido", "invalid_json")

    start = payload.get("start")
    end = payload.get("end")
    if start is None or end is None:
        return _trim_error(
            "Indica el inicio y el final del clip.", "invalid_range"
        )

    duration_s = clip.video.duration_s
    error, code = validate_range(start, end, duration_s)
    if error:
        return _trim_error(error, code)

    clip.start_time = float(start)
    clip.end_time = float(end)
    clip.edited = True
    clip.recut_status = Clip.RecutStatus.PROCESSING
    clip.save(
        update_fields=["start_time", "end_time", "edited", "recut_status"]
    )

    try:
        recut_clip.delay(clip.pk)
    except Exception:
        Clip.objects.filter(pk=clip.pk).update(
            recut_status=Clip.RecutStatus.FAILED
        )
        return _trim_error(
            "No se pudo encolar el re-recorte. Inténtalo de nuevo.",
            "recut_enqueue_failed",
            status=503,
        )

    return JsonResponse({"status": "processing", "clip": clip.pk}, status=202)


@login_required_json
def clip_status(request, pk):
    clip = _get_clip(request, pk)
    return JsonResponse(
        {
            "status": clip.recut_status,
            "clip": clip.pk,
            "start": clip.start_time,
            "end": clip.end_time,
            "edited": clip.edited,
        }
    )


@login_required_json
@require_POST
def clip_restore(request, pk):
    clip = _get_clip(request, pk)

    if not clip.edited:
        return JsonResponse(
            {"status": "ready", "clip": clip.pk, "message": "El clip no tenía cambios."}
        )
    if clip.orig_start_time is None or clip.orig_end_time is None:
        return _trim_error(
            "El clip no tiene un recorte original de la IA.", "no_original"
        )
    if clip.recut_status == Clip.RecutStatus.PROCESSING:
        return _trim_error(
            "Ya hay un re-recorte en curso para este clip.",
            "recut_in_progress",
            status=409,
        )

    clip.start_time = clip.orig_start_time
    clip.end_time = clip.orig_end_time
    clip.edited = False
    clip.recut_status = Clip.RecutStatus.PROCESSING
    clip.save(
        update_fields=["start_time", "end_time", "edited", "recut_status"]
    )

    try:
        recut_clip.delay(clip.pk)
    except Exception:
        Clip.objects.filter(pk=clip.pk).update(
            recut_status=Clip.RecutStatus.FAILED
        )
        return _trim_error(
            "No se pudo encolar el re-recorte. Inténtalo de nuevo.",
            "recut_enqueue_failed",
            status=503,
        )

    return JsonResponse({"status": "processing", "clip": clip.pk})


@login_required
@require_POST
def clip_delete(request, pk):
    clip = _get_clip(request, pk)
    video_pk = clip.video_id
    delete_clip_files(clip)
    clip.delete()
    messages.success(request, "El clip y sus archivos se eliminaron.")
    return redirect("video_clips", pk=video_pk)
