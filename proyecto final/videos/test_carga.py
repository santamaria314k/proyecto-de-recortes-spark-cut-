import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from pipeline.download import UnsafeURLError, validate_url

from .forms import VideoForm
from .models import Video


def _upload(name="video.mp4", size=1024):
    return SimpleUploadedFile(name, b"0" * size, content_type="video/mp4")


def test_form_accepts_allowed_extension():
    form = VideoForm(
        data={"title": "Demo", "source_type": "upload", "source_url": ""},
        files={"file": _upload("charla.MKV")},
    )

    assert form.is_valid(), form.errors


def test_form_rejects_other_extension():
    form = VideoForm(
        data={"title": "Demo", "source_type": "upload", "source_url": ""},
        files={"file": _upload("charla.exe")},
    )

    assert not form.is_valid()
    assert "file" in form.errors


def test_form_rejects_file_over_limit(settings):
    settings.MAX_VIDEO_SIZE_MB = 0
    form = VideoForm(
        data={"title": "Demo", "source_type": "upload", "source_url": ""},
        files={"file": _upload()},
    )

    assert not form.is_valid()
    assert "tamaño máximo" in str(form.errors["file"])


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/video",
        "http://localhost:8000/video",
        "http://127.0.0.1/video",
        "http://10.0.0.5/video",
        "http://169.254.169.254/latest/meta-data",
        "http://mysql.cluster.local/video",
    ],
)
def test_validate_url_rejects_internal_or_bad_scheme(url):
    with pytest.raises(UnsafeURLError):
        validate_url(url)


def test_validate_url_accepts_public_https():
    assert validate_url("https://www.youtube.com/watch?v=abc") == (
        "https://www.youtube.com/watch?v=abc"
    )


def test_form_rejects_internal_url():
    form = VideoForm(
        data={
            "title": "Demo",
            "source_type": "url",
            "source_url": "http://192.168.1.10/video",
        }
    )

    assert not form.is_valid()
    assert "source_url" in form.errors


@pytest.mark.django_db
def test_delete_removes_video_and_clip_files(logged_client, user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    video = Video.objects.create(
        user=user, title="Demo", source_type=Video.SourceType.UPLOAD
    )
    video.file.save("demo.mp4", SimpleUploadedFile("demo.mp4", b"video"), save=True)

    clip = video.clips.create(start_time=0, end_time=10, score=80)
    clip.file.save("clip.mp4", SimpleUploadedFile("clip.mp4", b"clip"), save=True)
    clip.thumbnail.save("thumb.jpg", SimpleUploadedFile("thumb.jpg", b"img"), save=True)

    video_path = video.file.path
    clip_path = clip.file.path
    thumb_path = clip.thumbnail.path

    response = logged_client.post(reverse("video_delete", args=[video.pk]))

    assert response.status_code == 302
    assert not Video.objects.filter(pk=video.pk).exists()
    for path in (video_path, clip_path, thumb_path):
        assert not __import__("os").path.exists(path)
