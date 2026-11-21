"""Formulario de carga de videos con las validaciones del spec."""

import os

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from pipeline.download import DownloadError, validate_url

from .models import Video

ALLOWED_EXTENSIONS = {"mp4", "mov", "mkv", "webm", "avi"}


class VideoForm(forms.ModelForm):
    class Meta:
        model = Video
        fields = ["title", "source_type", "source_url", "file"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Título del video"}),
            "source_url": forms.URLInput(attrs={"placeholder": "https://..."}),
            "file": forms.FileInput(attrs={"accept": ".mp4,.mov,.mkv,.webm,.avi"}),
        }

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if not uploaded or not hasattr(uploaded, "name"):
            return uploaded

        extension = os.path.splitext(uploaded.name)[1].lower().lstrip(".")
        if extension not in ALLOWED_EXTENSIONS:
            raise ValidationError(
                "Formato no permitido. Usa un archivo mp4, mov, mkv, webm o avi."
            )

        max_mb = settings.MAX_VIDEO_SIZE_MB
        if uploaded.size > max_mb * 1024 * 1024:
            raise ValidationError(
                f"El archivo supera el tamaño máximo de {max_mb} MB."
            )
        return uploaded

    def clean_source_url(self):
        url = (self.cleaned_data.get("source_url") or "").strip()
        if not url:
            return url
        try:
            validate_url(url)
        except DownloadError as exc:
            raise ValidationError(str(exc)) from exc
        return url

    def clean(self):
        cleaned = super().clean()
        source_type = cleaned.get("source_type")
        if source_type == Video.SourceType.UPLOAD and not cleaned.get("file"):
            self.add_error("file", "Selecciona un archivo de video.")
        if source_type == Video.SourceType.URL and not cleaned.get("source_url"):
            self.add_error("source_url", "Escribe una URL válida.")
        return cleaned
