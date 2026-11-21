"""Generación de ventanas candidatas (10–45 s) a partir de la transcripción.

Las ventanas se construyen acumulando segmentos consecutivos, se cierran antes
de superar el máximo y solo se emiten si alcanzan el mínimo. Los segmentos que
por sí solos superan el máximo se parten por palabras, repartiendo el tiempo de
forma proporcional al texto.

Cada ventana conserva el texto original (idioma del video) para mostrarlo al
usuario y, si la transcripción tiene traducción, `text_en` para el modelo.
"""

import math

MIN_DURATION = 10.0
MAX_DURATION = 45.0


def _clean(text) -> str:
    return " ".join(str(text or "").split())


def _split_words(words: list[str], count: int) -> list[str]:
    chunks = []
    for index in range(count):
        first = round(len(words) * index / count)
        last = round(len(words) * (index + 1) / count)
        chunks.append(" ".join(words[first:last]))
    return chunks


def _split_long_segment(segment: dict, max_duration: float) -> list[dict]:
    start = float(segment["start"])
    end = float(segment["end"])
    duration = end - start
    original = _clean(segment.get("text"))
    english = _clean(segment.get("text_en"))

    if duration <= max_duration:
        if not (original or english):
            return []
        chunk = {"start": start, "end": end, "text": original or english}
        if english and original:
            chunk["text_en"] = english
        return [chunk]

    word_count = max(len(original.split()), len(english.split()))
    if not word_count:
        return []

    pieces = min(int(math.ceil(duration / max_duration)), word_count)
    original_chunks = _split_words(original.split(), pieces)
    english_chunks = _split_words(english.split(), pieces) if english else []

    chunks = []
    for index in range(pieces):
        chunk_start = start + duration * index / pieces
        chunk_end = start + duration * (index + 1) / pieces
        text = original_chunks[index].strip() or (
            english_chunks[index].strip() if english_chunks else ""
        )
        if not text:
            continue
        chunk = {"start": chunk_start, "end": chunk_end, "text": text}
        if english_chunks and english_chunks[index].strip():
            chunk["text_en"] = english_chunks[index].strip()
        chunks.append(chunk)
    return chunks


def _append_window(windows: list[dict], window: dict, min_duration: float) -> None:
    if window["end"] - window["start"] >= min_duration:
        item = {
            "start": float(window["start"]),
            "end": float(window["end"]),
            "text": window["text"],
        }
        if window.get("text_en"):
            item["text_en"] = window["text_en"]
        windows.append(item)


def _merge(current: dict, segment: dict) -> None:
    current["end"] = segment["end"]
    current["text"] = f"{current['text']} {segment['text']}".strip()
    if current.get("text_en") and segment.get("text_en"):
        current["text_en"] = f"{current['text_en']} {segment['text_en']}".strip()
    else:
        current.pop("text_en", None)


def build_windows(
    segments,
    min_duration: float = MIN_DURATION,
    max_duration: float = MAX_DURATION,
) -> list[dict]:
    """Devuelve ventanas `{start, end, text, text_en?}` entre `min_duration` y `max_duration`."""
    expanded: list[dict] = []
    for segment in segments or []:
        expanded.extend(_split_long_segment(segment, max_duration))

    windows: list[dict] = []
    current: dict | None = None

    for segment in expanded:
        if segment["end"] <= segment["start"]:
            continue

        if current is None:
            current = dict(segment)
            continue

        if segment["end"] - current["start"] > max_duration:
            _append_window(windows, current, min_duration)
            current = dict(segment)
            continue

        _merge(current, segment)
        if current["end"] - current["start"] >= max_duration:
            _append_window(windows, current, min_duration)
            current = None

    if current is not None:
        _append_window(windows, current, min_duration)

    return windows
