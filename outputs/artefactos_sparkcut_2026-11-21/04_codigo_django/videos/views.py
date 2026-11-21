import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import login_required_json
from clips.utils import delete_video_files

from .forms import VideoForm
from .models import Video
from .tasks import process_video

logger = logging.getLogger(__name__)


@login_required
def dashboard(request):
    videos = Video.objects.filter(user=request.user)
    return render(request, "dashboard.html", {"videos": videos})


@login_required
def video_new(request):
    if request.method == "POST":
        form = VideoForm(request.POST, request.FILES)
        if form.is_valid():
            video = form.save(commit=False)
            video.user = request.user
            video.save()
            try:
                process_video.delay(video.pk)
            except Exception:
                logger.exception("No se pudo encolar el video %s", video.pk)
                video.status = Video.Status.FAILED
                video.error = (
                    "No se pudo encolar el procesamiento. Revisa que el worker "
                    "y Redis estén disponibles e inténtalo de nuevo."
                )
                video.save(update_fields=["status", "error"])
            return redirect("video_detail", pk=video.pk)
    else:
        form = VideoForm()
    return render(request, "videos/new.html", {"form": form})


@login_required
def video_detail(request, pk):
    video = get_object_or_404(Video, pk=pk, user=request.user)
    return render(request, "videos/detail.html", {"video": video})


@login_required_json
def video_status(request, pk):
    video = get_object_or_404(Video, pk=pk, user=request.user)
    return JsonResponse(
        {
            "status": video.status,
            "status_display": video.get_status_display(),
            "progress": video.progress,
            "error": video.error,
            "clips_count": video.clips.count(),
        }
    )


@login_required
@require_POST
def video_delete(request, pk):
    video = get_object_or_404(Video, pk=pk, user=request.user)
    delete_video_files(video)
    video.delete()
    messages.success(request, "El video y sus archivos se eliminaron.")
    return redirect("dashboard")


@login_required
def video_clips(request, pk):
    video = get_object_or_404(Video, pk=pk, user=request.user)
    clips = video.clips.all()
    return render(request, "videos/clips.html", {"video": video, "clips": clips})
