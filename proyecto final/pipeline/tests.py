import json
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

from pipeline import audio, cut, download, transcribe, windows
from pipeline.errors import DependencyMissingError, PipelineError
from pipeline.select import select_clips


def _completed(stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


# --- audio -----------------------------------------------------------------


def test_probe_duration_reads_ffprobe(monkeypatch):
    monkeypatch.setattr(
        audio.subprocess,
        "run",
        lambda *args, **kwargs: _completed(
            json.dumps({"format": {"duration": "123.4"}})
        ),
    )

    assert audio.probe_duration("video.mp4") == pytest.approx(123.4)


def test_validate_video_rejects_too_long(monkeypatch):
    monkeypatch.setattr(audio, "probe_duration", lambda path: 1300.0)

    with pytest.raises(audio.MediaError, match="máximo permitido"):
        audio.validate_video("video.mp4", max_duration_s=1200)


def test_validate_video_requires_audio(monkeypatch):
    monkeypatch.setattr(audio, "probe_duration", lambda path: 20.0)
    monkeypatch.setattr(audio, "has_audio", lambda path: False)

    with pytest.raises(audio.NoAudioError, match="pista de audio"):
        audio.validate_video("video.mp4")


def test_missing_ffmpeg_is_dependency_error(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(audio.subprocess, "run", missing)

    with pytest.raises(DependencyMissingError):
        audio.probe_duration("video.mp4")


def test_extract_audio_builds_ffmpeg_command(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _completed()

    monkeypatch.setattr(audio.subprocess, "run", fake_run)
    output = audio.extract_audio("video.mp4", tmp_path / "audio.wav")

    assert output == tmp_path / "audio.wav"
    assert calls[0][:2] == ["ffmpeg", "-y"]
    assert "-vn" in calls[0]
    assert calls[0][-1].endswith("audio.wav")


# --- transcribe ------------------------------------------------------------


def test_transcribe_without_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)

    with pytest.raises(DependencyMissingError):
        transcribe.transcribe("audio.wav")


def test_transcribe_empty_audio_raises(monkeypatch):
    module = ModuleType("faster_whisper")

    class FakeModel:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, *args, **kwargs):
            return iter([]), SimpleNamespace(language="es")

    module.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", module)
    # El decodificado del WAV se prueba con medios reales (requiere numpy).
    monkeypatch.setattr(transcribe, "_read_wav", lambda audio_path: [])

    with pytest.raises(transcribe.TranscriptionError, match="No se encontró voz"):
        transcribe.transcribe("audio.wav")


# --- download --------------------------------------------------------------


def test_download_returns_largest_file(monkeypatch, tmp_path):
    module = ModuleType("yt_dlp")

    class FakeYDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def download(self, urls):
            (tmp_path / "small.mp4").write_bytes(b"x")
            (tmp_path / "big.mp4").write_bytes(b"y" * 10)

    module.YoutubeDL = FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", module)

    assert download.download("https://example.com/video", tmp_path) == tmp_path / "big.mp4"


def test_download_without_dependency(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "yt_dlp", None)

    with pytest.raises(DependencyMissingError):
        download.download("https://example.com/video", tmp_path)


# --- windows ---------------------------------------------------------------


def _segments(count: int, duration: float = 12.0) -> list[dict]:
    return [
        {
            "start": index * duration,
            "end": (index + 1) * duration,
            "text": f"Frase número {index}.",
        }
        for index in range(count)
    ]


def test_windows_respect_min_and_max():
    result = windows.build_windows(_segments(3))

    assert len(result) == 1
    assert result[0]["start"] == 0
    assert result[0]["end"] == 36
    assert 10 <= result[0]["end"] - result[0]["start"] <= 45


def test_windows_discard_short_tail():
    result = windows.build_windows(_segments(1, duration=5.0))

    assert result == []


def test_long_segment_is_split_within_max():
    result = windows.build_windows(
        [{"start": 0.0, "end": 100.0, "text": " ".join(f"p{i}" for i in range(100))}]
    )

    assert len(result) == 3
    assert all(segment["end"] - segment["start"] <= 45 for segment in result)
    assert all(segment["text"] for segment in result)


def test_windows_keep_original_and_english_text():
    segments = [
        {"start": 0.0, "end": 20.0, "text": "Hola mundo.", "text_en": "Hello world."}
    ]

    result = windows.build_windows(segments)

    assert result[0]["text"] == "Hola mundo."
    assert result[0]["text_en"] == "Hello world."


def test_long_segment_with_translation_splits_both_texts():
    original = " ".join(f"p{i}" for i in range(40))
    english = " ".join(f"e{i}" for i in range(25))

    result = windows.build_windows(
        [{"start": 0.0, "end": 100.0, "text": original, "text_en": english}]
    )

    assert len(result) == 3
    assert [word for window in result for word in window["text"].split()] == original.split()
    assert [word for window in result for word in window["text_en"].split()] == english.split()
    assert all(window["end"] - window["start"] <= 45 for window in result)


# --- select ----------------------------------------------------------------


def _window(start: float, end: float, text: str = "texto") -> dict:
    return {"start": start, "end": end, "text": text}


def test_threshold_is_strict():
    result = select_clips(
        [_window(0, 20), _window(30, 50)],
        [70.0, 90.0],
    )

    assert len(result) == 1
    assert result[0]["score"] == 90.0
    assert result[0]["tier"] == "high"


def test_overlap_over_limit_is_rejected():
    result = select_clips(
        [_window(0, 20), _window(5, 25)],
        [90.0, 85.0],
    )

    assert len(result) == 1
    assert result[0]["start"] == 0


def test_max_ten_clips():
    windows = [_window(index * 30, index * 30 + 20) for index in range(12)]
    scores = [100.0 - index for index in range(12)]

    result = select_clips(windows, scores)

    assert len(result) == 10
    assert all(spec["tier"] == "high" for spec in result)


def test_fallback_returns_top_three_medium():
    windows = [_window(index * 30, index * 30 + 20) for index in range(4)]
    scores = [60.0, 55.0, 50.0, 45.0]

    result = select_clips(windows, scores)

    assert len(result) == 3
    assert all(spec["tier"] == "medium" for spec in result)
    assert [spec["score"] for spec in result] == [60.0, 55.0, 50.0]


def test_fallback_with_fewer_than_three_candidates():
    result = select_clips([_window(0, 20), _window(30, 50)], [50.0, 40.0])

    assert len(result) == 2
    assert all(spec["tier"] == "medium" for spec in result)


def test_select_rejects_mismatched_lengths():
    with pytest.raises(PipelineError):
        select_clips([_window(0, 20)], [])


# --- cut -------------------------------------------------------------------


def test_cut_clip_uses_frame_accurate_command(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(cut, "run_ffmpeg", lambda cmd: calls.append(cmd) or _completed())

    output = cut.cut_clip("video.mp4", 5.0, 30.0, tmp_path / "clip.mp4")

    assert output == tmp_path / "clip.mp4"
    command = calls[0]
    assert command[0] == "ffmpeg"
    assert command.index("-ss") > command.index("-i")
    assert command[command.index("-t") + 1] == "25.000"


def test_make_thumbnail_uses_first_frame(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(cut, "run_ffmpeg", lambda cmd: calls.append(cmd) or _completed())

    output = cut.make_thumbnail("video.mp4", 12.0, tmp_path / "thumb.jpg")

    assert output == tmp_path / "thumb.jpg"
    assert "-frames:v" in calls[0]
    assert "scale=480:-2" in calls[0]


# --- transcribe / traducción ------------------------------------------------


def _wav(path, seconds: float = 12.0):
    import wave

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * int(16000 * seconds))
    return path


def _fake_whisper(monkeypatch, detected_language: str = "es", translate_error=None):
    """Instala un faster_whisper falso y devuelve la lista de pasadas usadas."""
    calls: list[str] = []

    class FakeWhisperModel:
        def __init__(self, size, device=None, compute_type=None):
            self.size = size

        def transcribe(self, samples, vad_filter=True, language=None, task="transcribe"):
            calls.append(task)
            if task == "translate":
                if translate_error:
                    raise translate_error
                items = [
                    SimpleNamespace(start=0.0, end=6.0, text=" Hello"),
                    SimpleNamespace(start=6.0, end=12.0, text=" world."),
                ]
            else:
                items = [
                    SimpleNamespace(start=0.0, end=6.0, text=" Hola"),
                    SimpleNamespace(start=6.0, end=12.0, text=" mundo."),
                ]
            return iter(items), SimpleNamespace(language=detected_language)

    module = ModuleType("faster_whisper")
    module.WhisperModel = FakeWhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", module)
    return calls


def test_transcribe_adds_english_text_for_non_english_audio(monkeypatch, tmp_path):
    calls = _fake_whisper(monkeypatch)

    result = transcribe.transcribe(_wav(tmp_path / "audio.wav"), model_size="tiny")

    assert calls == ["transcribe", "translate"]
    assert result["language"] == "es"
    assert [segment["text"] for segment in result["segments"]] == ["Hola", "mundo."]
    assert [segment["text_en"] for segment in result["segments"]] == ["Hello", "world."]


def test_transcribe_skips_translation_for_english_audio(monkeypatch, tmp_path):
    calls = _fake_whisper(monkeypatch, detected_language="en")

    result = transcribe.transcribe(_wav(tmp_path / "audio.wav"), model_size="tiny")

    assert calls == ["transcribe"]
    assert all("text_en" not in segment for segment in result["segments"])


def test_transcribe_keeps_original_when_translation_fails(monkeypatch, tmp_path):
    _fake_whisper(monkeypatch, translate_error=RuntimeError("sin red"))

    result = transcribe.transcribe(_wav(tmp_path / "audio.wav"), model_size="tiny")

    assert [segment["text"] for segment in result["segments"]] == ["Hola", "mundo."]
    assert all("text_en" not in segment for segment in result["segments"])
