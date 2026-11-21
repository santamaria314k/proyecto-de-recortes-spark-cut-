# Tasks

## 1. Módulos puros del pipeline

- [x] 1.1 Añadir `pipeline/errors.py` con `PipelineError`, `DependencyMissingError` y los errores de medios; verificar con pruebas de mensaje legible.
- [x] 1.2 Implementar `pipeline/audio.py` (`probe_duration`, `has_audio`, `validate_video`, `extract_audio`) con `subprocess` sin shell; verificar con dobles de `subprocess.run` (duración, sin audio, ffmpeg ausente).
- [x] 1.3 Implementar `pipeline/transcribe.py` con import diferido de `faster_whisper`, segmentos ordenados y error si no hay voz; verificar con pruebas de import ausente y transcripción vacía.
- [x] 1.4 Implementar `pipeline/download.py` con import diferido de `yt_dlp` y error legible ante fallo de descarga; verificar con dobles.
- [x] 1.5 Implementar `pipeline/windows.py` (ventanas de 10–45 s alineadas a segmentos, sin solape y división de segmentos largos); verificar con pruebas de bordes.
- [x] 1.6 Implementar `pipeline/select.py` (umbral estricto > 70, máximo 10, solape ≤ 30 %, respaldo de 3 `medium`); verificar con pruebas de umbral, solape y respaldo.
- [x] 1.7 Implementar `pipeline/cut.py` (`cut_clip` y `make_thumbnail` con ffmpeg y recodificación); verificar con dobles de `run_ffmpeg`.

## 2. Tarea `process_video`

- [x] 2.1 Implementar el flujo completo (descarga opcional → validación → transcripción → ventanas → puntuación → selección → recorte) con estados y progreso por fase; verificar con una prueba de éxito con dobles.
- [x] 2.2 Persistir `Transcript` y los `Clip` (con `orig_start_time`, `orig_end_time`, explicación y archivos en el almacén de medios); verificar con la prueba de éxito.
- [x] 2.3 Manejar fallos: `failed` con mensaje legible, traza en el log, sin clips parciales y sin temporales; verificar con pruebas de fallo de recorte y de transcripción vacía.
- [x] 2.4 Aplicar el límite de tiempo configurable con `soft_time_limit`/`time_limit` y capturar `SoftTimeLimitExceeded`; verificar con la prueba de la tarea y la configuración.

## 3. Configuración y documentación

- [x] 3.1 Añadir `WHISPER_MODEL`, `MAX_VIDEO_DURATION_S` y `PIPELINE_TIME_LIMIT_S` a `settings.py`, `.env.example` y `README.md`; verificar con `manage.py check`.
- [x] 3.2 Añadir `faster-whisper` y `yt-dlp` a `requirements.txt`; verificar que el import diferido deja correr las pruebas sin ellos.
- [x] 3.3 Actualizar la sección «Estado» del `README.md` (pipeline real y requisito de ffmpeg); verificar la documentación.

## 4. Verificación

- [x] 4.1 Ejecutar `pytest` completo y corregir los fallos.
- [x] 4.2 Ejecutar `python manage.py check` y `openspec validate --change real-pipeline`.
