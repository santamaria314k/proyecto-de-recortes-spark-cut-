import json
import os
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from videos.models import Video

from .models import Clip


@pytest.fixture
def clip(db, user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    video = Video.objects.create(
        user=user,
        title="Demo",
        source_type=Video.SourceType.UPLOAD,
        status=Video.Status.DONE,
        duration_s=120,
    )
    video.file.save("demo.mp4", SimpleUploadedFile("demo.mp4", b"video"), save=True)

    instance = Clip.objects.create(
        video=video,
        start_time=10,
        end_time=40,
        orig_start_time=10,
        orig_end_time=40,
        score=90,
        tier=Clip.Tier.HIGH,
        text="Texto de prueba",
    )
    instance.file.save(
        "clip.mp4", SimpleUploadedFile("clip.mp4", b"0123456789"), save=True
    )
    return instance


def test_media_without_range_returns_200(logged_client, clip):
    response = logged_client.get(reverse("clip_media", args=[clip.pk]))

    assert response.status_code == 200
    assert response["Accept-Ranges"] == "bytes"


def test_media_with_range_returns_206(logged_client, clip):
    response = logged_client.get(
        reverse("clip_media", args=[clip.pk]), headers={"Range": "bytes=0-3"}
    )

    assert response.status_code == 206
    assert response["Content-Range"] == "bytes 0-3/10"
    assert b"".join(response.streaming_content) == b"0123"


def test_media_with_invalid_range_returns_416(logged_client, clip):
    response = logged_client.get(
        reverse("clip_media", args=[clip.pk]), headers={"Range": "bytes=999-"}
    )

    assert response.status_code == 416
    assert response["Content-Range"] == "bytes */10"


def test_trim_valid_updates_clip_and_enqueues(logged_client, clip):
    with patch("clips.views.recut_clip.delay") as delay:
        response = logged_client.post(
            reverse("clip_trim", args=[clip.pk]),
            data=json.dumps({"start": 12, "end": 45}),
            content_type="application/json",
        )

    assert response.status_code == 202
    clip.refresh_from_db()
    assert (clip.start_time, clip.end_time) == (12, 45)
    assert clip.edited is True
    assert clip.recut_status == Clip.RecutStatus.PROCESSING
    delay.assert_called_once_with(clip.pk)


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"start": 30, "end": 20}, "invalid_range"),
        ({"start": 10, "end": 11}, "invalid_duration"),
        ({"start": 118, "end": 121}, "out_of_bounds"),
        ({"start": 10}, "invalid_range"),
    ],
)
def test_trim_rejects_invalid_ranges(logged_client, clip, payload, code):
    response = logged_client.post(
        reverse("clip_trim", args=[clip.pk]),
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == code


def test_trim_conflicts_when_recut_in_progress(logged_client, clip):
    Clip.objects.filter(pk=clip.pk).update(recut_status=Clip.RecutStatus.PROCESSING)

    response = logged_client.post(
        reverse("clip_trim", args=[clip.pk]),
        data=json.dumps({"start": 12, "end": 45}),
        content_type="application/json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "recut_in_progress"


def test_trim_requires_json(logged_client, clip):
    response = logged_client.post(
        reverse("clip_trim", args=[clip.pk]), data="no json", content_type="application/json"
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_json"


def test_restore_returns_to_original_times(logged_client, clip):
    Clip.objects.filter(pk=clip.pk).update(
        start_time=20, end_time=50, edited=True
    )

    with patch("clips.views.recut_clip.delay") as delay:
        response = logged_client.post(reverse("clip_restore", args=[clip.pk]))

    assert response.status_code == 200
    clip.refresh_from_db()
    assert (clip.start_time, clip.end_time) == (10, 40)
    assert clip.edited is False
    delay.assert_called_once_with(clip.pk)


def test_restore_without_changes_is_noop(logged_client, clip):
    response = logged_client.post(reverse("clip_restore", args=[clip.pk]))

    assert response.status_code == 200
    assert response.json()["message"] == "El clip no tenía cambios."


def test_status_reports_recut_state(logged_client, clip):
    response = logged_client.get(reverse("clip_status", args=[clip.pk]))

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_delete_removes_clip_files(logged_client, clip):
    clip_path = clip.file.path

    response = logged_client.post(reverse("clip_delete", args=[clip.pk]))

    assert response.status_code == 302
    assert not Clip.objects.filter(pk=clip.pk).exists()
    assert not os.path.exists(clip_path)


def test_clip_endpoints_reject_anonymous_json(client, clip):
    response = client.post(
        reverse("clip_trim", args=[clip.pk]),
        data=json.dumps({"start": 12, "end": 45}),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["code"] == "not_authenticated"
