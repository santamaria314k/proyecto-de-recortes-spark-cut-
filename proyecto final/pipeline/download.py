"""Descarga de videos desde enlaces con yt-dlp.

Incluye la validación de la URL para evitar peticiones a recursos internos
(SSRF), tal como exige el spec de gestión de videos.
"""

import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlsplit

from .errors import DependencyMissingError, PipelineError


class DownloadError(PipelineError):
    """No se pudo descargar el video del enlace."""


class UnsafeURLError(DownloadError):
    """La URL apunta a un recurso interno o no permitido."""


BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}
BLOCKED_SUFFIXES = (".local", ".internal", ".localhost", ".cluster.local")


def _is_blocked_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_reserved,
            address.is_multicast,
            address.is_unspecified,
        )
    )


def validate_url(url: str) -> str:
    """Valida el esquema y el host literal de la URL, sin resolver DNS."""
    url = (url or "").strip()
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise UnsafeURLError("El enlace debe empezar por http:// o https://.")
    if not parts.hostname:
        raise UnsafeURLError("El enlace no tiene un dominio válido.")

    host = parts.hostname.rstrip(".").lower()
    if host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_SUFFIXES):
        raise UnsafeURLError(
            "El enlace apunta a una dirección interna y no se puede usar."
        )
    if _is_blocked_ip(host):
        raise UnsafeURLError(
            "El enlace apunta a una dirección privada o local y no se puede usar."
        )
    return url


def resolve_and_validate(url: str) -> str:
    """Valida la URL y comprueba que el dominio resuelva a una IP pública."""
    url = validate_url(url)
    host = urlsplit(url).hostname
    try:
        addresses = {
            info[4][0] for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        }
    except socket.gaierror as exc:
        raise DownloadError("No se pudo resolver el dominio del enlace.") from exc

    for address in addresses:
        if _is_blocked_ip(address):
            raise UnsafeURLError(
                "El enlace resuelve a una dirección interna y no se puede usar."
            )
    return url


def probe_duration(url: str):
    """Devuelve la duración anunciada por yt-dlp antes de descargar, o None."""
    try:
        import yt_dlp
    except ImportError as exc:
        raise DependencyMissingError(
            "yt-dlp no está instalado en el worker de procesamiento."
        ) from exc

    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:  # los metadatos son opcionales: el fallo real llega en la descarga
        return None

    if not isinstance(info, dict):
        return None
    duration = info.get("duration")
    try:
        duration = float(duration)
    except (TypeError, ValueError):
        return None
    return duration if duration > 0 else None


def download(url: str, out_dir) -> Path:
    """Descarga el video en `out_dir` y devuelve el archivo resultante."""
    validate_url(url)
    try:
        import yt_dlp
    except ImportError as exc:
        raise DependencyMissingError(
            "yt-dlp no está instalado en el worker de procesamiento."
        ) from exc

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    options = {
        "outtmpl": str(out_dir / "%(title).150B-%(id)s.%(ext)s"),
        "format": "mp4/bestvideo*+bestaudio/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
    except Exception as exc:  # yt-dlp lanza muchos tipos de error distintos
        raise DownloadError(
            "No se pudo descargar el video del enlace. Intenta subir el archivo local."
        ) from exc

    files = sorted(
        (path for path in out_dir.iterdir() if path.is_file()),
        key=lambda path: path.stat().st_size,
        reverse=True,
    )
    if not files:
        raise DownloadError("La descarga del enlace no produjo ningún archivo.")
    return files[0]
