import pytest

from videos.models import Video

from .models import Clip


@pytest.mark.django_db
def test_clip_creation(user):
    video = Video.objects.create(user=user, title="Demo", source_type=Video.SourceType.UPLOAD)
    clip = Clip.objects.create(
        video=video,
        start_time=10,
        end_time=40,
        score=82.5,
        tier=Clip.Tier.HIGH,
        text="Un fragmento de prueba",
    )

    assert clip.tier == Clip.Tier.HIGH
    assert clip.edited is False
    assert str(clip) == f"Clip {clip.pk} de {video.pk}"
