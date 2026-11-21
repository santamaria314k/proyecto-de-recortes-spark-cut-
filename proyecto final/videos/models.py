from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Video(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        DOWNLOADING = "downloading", "Descargando"
        TRANSCRIBING = "transcribing", "Transcribiendo"
        SCORING = "scoring", "Puntuando"
        CLIPPING = "clipping", "Recortando"
        DONE = "done", "Listo"
        FAILED = "failed", "Fallido"

    class SourceType(models.TextChoices):
        UPLOAD = "upload", "Archivo"
        URL = "url", "Enlace"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="videos",
    )
    title = models.CharField(max_length=255)
    source_type = models.CharField(
        max_length=10,
        choices=SourceType.choices,
        default=SourceType.UPLOAD,
    )
    source_url = models.URLField(blank=True)
    file = models.FileField(upload_to="videos/", blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    progress = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    error = models.TextField(blank=True)
    duration_s = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MaxValueValidator(1200)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "created_at"])]
        constraints = [
            models.CheckConstraint(
                check=models.Q(progress__gte=0, progress__lte=100),
                name="video_progress_range",
            )
        ]

    def __str__(self):
        return self.title

    def clean(self):
        if self.source_type == self.SourceType.UPLOAD and not self.file:
            raise ValidationError({"file": "La subida por archivo requiere un archivo."})
        if self.source_type == self.SourceType.URL and not self.source_url:
            raise ValidationError({"source_url": "La subida por enlace requiere una URL."})
        if self.duration_s is not None and self.duration_s > 1200:
            raise ValidationError({"duration_s": "La duración máxima es de 1200 segundos."})


class Transcript(models.Model):
    video = models.OneToOneField(
        Video,
        on_delete=models.CASCADE,
        related_name="transcript",
    )
    language = models.CharField(max_length=10, default="es")
    segments = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transcripción de {self.video_id}"
