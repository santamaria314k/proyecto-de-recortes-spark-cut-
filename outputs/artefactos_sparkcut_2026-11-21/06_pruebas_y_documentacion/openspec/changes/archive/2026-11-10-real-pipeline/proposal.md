# Proposal

## Why

El andamiaje de `bootstrap-sparkcut` dejó la tarea `process_video` simulada: avanza estados y termina en
`done` sin producir transcripción ni clips. El objetivo del producto (RF-07..RF-13) todavía no ocurre y
la interfaz no tiene nada que mostrar.

Este cambio sustituye la simulación por el pipeline real, manteniendo la firma pública de la tarea y los
contratos de módulos descritos en `openspec/project.md`.

## What Changes

- Añadir los módulos puros `pipeline.audio` (ffprobe/ffmpeg), `pipeline.transcribe` (faster-whisper),
  `pipeline.download` (yt-dlp), `pipeline.windows`, `pipeline.select` y `pipeline.cut` (ffmpeg).
- Sustituir el cuerpo de `videos.tasks.process_video` por el flujo completo:
  descarga opcional → validación de duración/audio → transcripción → ventanas → puntuación →
  selección → recorte y miniaturas → persistencia en `Transcript` y `Clip`.
- Actualizar `status` y `progress` por fase (`downloading` 10, `transcribing` 40, `scoring` 70,
  `clipping` 90, `done` 100) y llevar a `failed` con mensaje legible ante cualquier error.
- Guardar los clips cortados en el almacén de medios y limpiar archivos temporales y clips parciales
  cuando el pipeline falla.
- Añadir el límite de tiempo configurable de la tarea y las dependencias `faster-whisper` y `yt-dlp`.
- Añadir pruebas unitarias de ventanas, selección, audio, recorte y de la tarea completa con dobles
  de prueba, sin ffmpeg, Whisper ni yt-dlp reales.

**Fuera de alcance de este cambio:** el modelo RNN real y la carga de `ml_artifacts` (se sigue usando
`scoring.scorer` simulado con `MOCK_SCORER=1`), la traducción automática al inglés (decisión pendiente en
`REFINAMIENTO.md`), el panel/editor de clips, la exportación 9:16 y los manifiestos de Kubernetes.

## Capabilities

### New Capabilities

Ninguna. La especificación `pipeline-de-procesamiento` ya define el comportamiento; este cambio la
implementa.

### Modified Capabilities

Ninguna. Los requisitos, escenarios y contratos de `openspec/specs/` no cambian.

> El cambio declara `skip_specs: true` por ser una implementación sin delta de comportamiento.

## Impact

- **Código:** `pipeline/` (audio, transcribe, download, windows, select, cut, errors), `videos/tasks.py`,
  `sparkcut/settings.py`.
- **Dependencias:** `faster-whisper` y `yt-dlp`; `ffmpeg`/`ffprobe` como binarios del sistema (imagen Docker).
- **Configuración:** nuevas variables `WHISPER_MODEL`, `MAX_VIDEO_DURATION_S` y `PIPELINE_TIME_LIMIT_S`
  con valores por defecto, documentadas en `.env.example` y `README.md`.
- **Contratos:** se respetan `Segment`, `Window`, `ClipSpec`, `score_segments`, `score_segments_detailed`,
  `select_clips` y `cut_clip` tal como están en `project.md`; no cambia ningún endpoint.
- **Riesgo:** las pruebas no ejecutan Whisper, yt-dlp ni ffmpeg reales; la verificación de integración
  con medios reales queda para una prueba manual con un video corto.
