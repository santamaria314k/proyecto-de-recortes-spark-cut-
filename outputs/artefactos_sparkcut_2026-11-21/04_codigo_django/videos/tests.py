from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from clips.models import Clip
from pipeline.errors import PipelineError

from .models import Transcript, Video
from .tasks import process_video


@pytest.mark.django_db
def test_create_video_defaults(user):
    video = Video.objects.create(
        user=user,
        title="Demo",
        source_type=Video.SourceType.UPLOAD,
    )
    assert video.status == Video.Status.PENDING
    assert video.progress == 0
    assert str(video) == "Demo"


@pytest.mark.django_db
def test_upload_requires_file(user):
    video = Video(user=user, title="Demo", source_type=Video.SourceType.UPLOAD)
    with pytest.raises(ValidationError):
        video.full_clean()


@pytest.mark.django_db
def test_url_requires_source_url(user):
    video = Video(user=user, title="Demo", source_type=Video.SourceType.URL)
    with pytest.raises(ValidationError):
        video.full_clean()


@pytest.mark.django_db
def test_clip_duration_validation(user):
    video = Video.objects.create(user=user, title="Demo", source_type=Video.SourceType.UPLOAD)
    clip = Clip(video=video, start_time=0, end_time=1, score=80)
    with pytest.raises(ValidationError):
        clip.full_clean()


@pytest.mark.django_db
def test_dashboard_requires_login(client):
    response = client.get(reverse("dashboard"))
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_dashboard_lists_only_own_videos(logged_client, user, other_user):
    Video.objects.create(user=user, title="Mío", source_type=Video.SourceType.UPLOAD)
    Video.objects.create(user=other_user, title="Ajeno", source_type=Video.SourceType.UPLOAD)

    response = logged_client.get(reverse("dashboard"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Mío" in content
    assert "Ajeno" not in content


@pytest.mark.django_db
def test_video_detail_404_for_other_user(logged_client, other_user):
    video = Video.objects.create(
        user=other_user,
        title="Ajeno",
        source_type=Video.SourceType.UPLOAD,
    )

    response = logged_client.get(reverse("video_detail", args=[video.pk]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_delete_video_cascades(user):
    video = Video.objects.create(user=user, title="Demo", source_type=Video.SourceType.UPLOAD)
    Transcript.objects.create(video=video, segments=[])
    Clip.objects.create(video=video, start_time=0, end_time=10, score=80)

    video.delete()

    assert Transcript.objects.count() == 0
    assert Clip.objects.count() == 0


SEGMENTS = [
    {
        "start": index * 12.0,
        "end": (index + 1) * 12.0,
        "text": f"Frase {index}.",
    }
    for index in range(6)
]


def _fake_cut(src, start, end, out):
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(b"clip")
    return Path(out)


def _fake_thumbnail(src, at, out):
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(b"thumb")
    return Path(out)


@pytest.mark.django_db
def test_process_video_runs_real_pipeline(user, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    video = Video.objects.create(
        user=user,
        title="Demo",
        source_type=Video.SourceType.UPLOAD,
        file="videos/demo.mp4",
    )

    with (
        patch("videos.tasks.validate_video", return_value=72.0),
        patch("videos.tasks.audio.extract_audio", return_value=tmp_path / "audio.wav"),
        patch(
            "videos.tasks.transcribe",
            return_value={"language": "es", "segments": SEGMENTS},
        ),
        patch("videos.tasks.score_segments", return_value=[90.0, 85.0]),
        patch(
            "videos.tasks.score_segments_detailed",
            return_value=[
                {"score": 90.0, "dims": {"hook": 90.0}, "top_emotions": []},
                {"score": 85.0, "dims": {"hook": 85.0}, "top_emotions": []},
            ],
        ),
        patch("videos.tasks.cut_clip", side_effect=_fake_cut),
        patch("videos.tasks.make_thumbnail", side_effect=_fake_thumbnail),
    ):
        process_video(video.pk)

    video.refresh_from_db()
    assert video.status == Video.Status.DONE
    assert video.progress == 100
    assert video.duration_s == 72
    assert video.error == ""

    transcript = Transcript.objects.get(video=video)
    assert transcript.language == "es"
    assert len(transcript.segments) == len(SEGMENTS)

    clips = list(video.clips.order_by("start_time"))
    assert len(clips) == 2
    assert [clip.score for clip in clips] == [90.0, 85.0]
    assert all(clip.tier == Clip.Tier.HIGH for clip in clips)
    assert clips[0].orig_start_time == clips[0].start_time
    assert clips[0].orig_end_time == clips[0].end_time
    assert clips[0].file.name.startswith("clips/")
    assert clips[0].thumbnail.name.startswith("thumbnails/")


@pytest.mark.django_db
def test_process_video_marks_failed_and_keeps_no_partial_clips(
    user, settings, tmp_path
):
    settings.MEDIA_ROOT = str(tmp_path)
    video = Video.objects.create(
        user=user,
        title="Demo",
        source_type=Video.SourceType.UPLOAD,
        file="videos/demo.mp4",
    )

    def failing_cut(src, start, end, out):
        raise PipelineError("No se pudo recortar el clip.")

    with (
        patch("videos.tasks.validate_video", return_value=72.0),
        patch("videos.tasks.audio.extract_audio", return_value=tmp_path / "audio.wav"),
        patch(
            "videos.tasks.transcribe",
            return_value={"language": "es", "segments": SEGMENTS},
        ),
        patch("videos.tasks.score_segments", return_value=[90.0, 85.0]),
        patch("videos.tasks.cut_clip", side_effect=failing_cut),
        pytest.raises(PipelineError),
    ):
        process_video(video.pk)

    video.refresh_from_db()
    assert video.status == Video.Status.FAILED
    assert video.error == "No se pudo recortar el clip."
    assert Clip.objects.filter(video=video).count() == 0


@pytest.mark.django_db
def test_process_video_cleans_clips_created_before_failure(user, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    video = Video.objects.create(
        user=user,
        title="Demo",
        source_type=Video.SourceType.UPLOAD,
        file="videos/demo.mp4",
    )

    def save_then_fail(video_obj, prepared, details, sink):
        sink.append(
            Clip.objects.create(
                video=video_obj, start_time=0, end_time=10, score=80
            )
        )
        raise PipelineError("Fallo al guardar los clips.")

    with (
        patch("videos.tasks.validate_video", return_value=72.0),
        patch("videos.tasks.audio.extract_audio", return_value=tmp_path / "audio.wav"),
        patch(
            "videos.tasks.transcribe",
            return_value={"language": "es", "segments": SEGMENTS},
        ),
        patch("videos.tasks.score_segments", return_value=[90.0, 85.0]),
        patch("videos.tasks.cut_clip", side_effect=_fake_cut),
        patch("videos.tasks.make_thumbnail", side_effect=_fake_thumbnail),
        patch("videos.tasks._save_clips", side_effect=save_then_fail),
        pytest.raises(PipelineError),
    ):
        process_video(video.pk)

    video.refresh_from_db()
    assert video.status == Video.Status.FAILED
    assert Clip.objects.filter(video=video).count() == 0


@pytest.mark.django_db
def test_process_video_fails_without_enough_speech(user, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    video = Video.objects.create(
        user=user,
        title="Demo",
        source_type=Video.SourceType.UPLOAD,
        file="videos/demo.mp4",
    )

    with (
        patch("videos.tasks.validate_video", return_value=5.0),
        patch("videos.tasks.audio.extract_audio", return_value=tmp_path / "audio.wav"),
        patch(
            "videos.tasks.transcribe",
            return_value={
                "language": "es",
                "segments": [{"start": 0.0, "end": 5.0, "text": "Muy corto."}],
            },
        ),
        pytest.raises(PipelineError, match="No hay voz suficiente"),
    ):
        process_video(video.pk)

    video.refresh_from_db()
    assert video.status == Video.Status.FAILED
    assert "No hay voz suficiente" in video.error
    assert Clip.objects.filter(video=video).count() == 0


def test_process_video_has_time_limits():
    assert process_video.soft_time_limit == 3600
    assert process_video.time_limit == 3660


@pytest.mark.django_db
def test_video_new_creates_video(logged_client, user):
    with patch("videos.views.process_video.delay") as delay:
        response = logged_client.post(
            reverse("video_new"),
            {
                "title": "Demo",
                "source_type": Video.SourceType.URL,
                "source_url": "https://example.com/video",
            },
        )

    assert response.status_code == 302
    video = Video.objects.get(user=user, title="Demo")
    delay.assert_called_once_with(video.pk)


@pytest.mark.django_db
def test_video_status_json(logged_client, user):
    video = Video.objects.create(
        user=user,
        title="Demo",
        source_type=Video.SourceType.UPLOAD,
        status=Video.Status.DONE,
        progress=100,
    )

    response = logged_client.get(reverse("video_status", args=[video.pk]))

    assert response.status_code == 200
    assert response.json() == {
        "status": "done",
        "status_display": "Listo",
        "progress": 100,
        "error": "",
        "clips_count": 0,
    }


@pytest.mark.django_db
def test_pipeline_scores_english_translation_and_keeps_original_text(
    user, settings, tmp_path
):
    settings.MEDIA_ROOT = str(tmp_path)
    video = Video.objects.create(
        user=user,
        title="Demo",
        source_type=Video.SourceType.UPLOAD,
        file="videos/demo.mp4",
    )
    segments = [
        dict(segment, text_en=f"Phrase {index}.")
        for index, segment in enumerate(SEGMENTS)
    ]
    seen = {}

    def fake_score(texts):
        seen["texts"] = list(texts)
        return [90.0, 85.0]

    with (
        patch("videos.tasks.validate_video", return_value=72.0),
        patch("videos.tasks.audio.extract_audio", return_value=tmp_path / "audio.wav"),
        patch(
            "videos.tasks.transcribe",
            return_value={"language": "es", "segments": segments},
        ),
        patch("videos.tasks.score_segments", side_effect=fake_score),
        patch(
            "videos.tasks.score_segments_detailed",
            return_value=[
                {"score": 90.0, "dims": {"hook": 90.0}, "top_emotions": []},
                {"score": 85.0, "dims": {"hook": 85.0}, "top_emotions": []},
            ],
        ),
        patch("videos.tasks.cut_clip", side_effect=_fake_cut),
        patch("videos.tasks.make_thumbnail", side_effect=_fake_thumbnail),
    ):
        process_video(video.pk)

    assert seen["texts"] == [
        "Phrase 0. Phrase 1. Phrase 2.",
        "Phrase 3. Phrase 4. Phrase 5.",
    ]
    clips = list(video.clips.order_by("start_time"))
    assert clips[0].text == "Frase 0. Frase 1. Frase 2."
