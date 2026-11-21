from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Clip(models.Model):
    class Tier(models.TextChoices):
        HIGH = "high", "Alto"
        MEDIUM = "medium", "Medio"

    class RecutStatus(models.TextChoices):
        PROCESSING = "processing", "Recortando"
        READY = "ready", "Listo"
        FAILED = "failed", "Fallido"

    video = models.ForeignKey(
        "videos.Video",
        on_delete=models.CASCADE,
        related_name="clips",
    )
    start_time = models.FloatField()
    end_time = models.FloatField()
    orig_start_time = models.FloatField(null=True, blank=True)
    orig_end_time = models.FloatField(null=True, blank=True)
    score = models.FloatField(
        validators=[MinValueValidator(10), MaxValueValidator(100)]
    )
    tier = models.CharField(
        max_length=10,
        choices=Tier.choices,
        default=Tier.MEDIUM,
    )
    text = models.TextField(blank=True)
    file = models.FileField(upload_to="clips/", blank=True, null=True)
    thumbnail = models.FileField(upload_to="thumbnails/", blank=True, null=True)
    explanation = models.JSONField(default=dict, blank=True)
    edited = models.BooleanField(default=False)
    recut_status = models.CharField(
        max_length=12,
        choices=RecutStatus.choices,
        default=RecutStatus.READY,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score"]
        indexes = [models.Index(fields=["video", "score"])]
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F("start_time")),
                name="clip_time_order",
            )
        ]

    def __str__(self):
        return f"Clip {self.pk} de {self.video_id}"

    def clean(self):
        if self.start_time is not None and self.end_time is not None:
            duration = self.end_time - self.start_time
            if duration < 3 or duration > 90:
                raise ValidationError(
                    {"end_time": "La duración del clip debe estar entre 3 y 90 segundos."}
                )
        if self.score is not None and not (10 <= self.score <= 100):
            raise ValidationError({"score": "El puntaje debe estar entre 10 y 100."})
