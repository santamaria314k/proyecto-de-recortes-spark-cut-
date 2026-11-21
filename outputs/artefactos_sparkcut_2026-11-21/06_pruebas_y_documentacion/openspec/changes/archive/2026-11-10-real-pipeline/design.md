# Design

## Context

Ver `proposal.md` para la motivación. Ya existen los modelos `Video`, `Transcript` y `Clip`, la tarea
simulada, el scorer simulado con `MOCK_SCORER=1` y la suite de humo. `project.md` fija los contratos:
módulos de IA/video en Python puro sin Django, la web nunca procesa video y `process_video(video_id)` es
la única entrada al pipeline.

Restricciones:

- Windows local con Python 3.12; ffmpeg no es una dependencia de Python y puede no estar instalado.
- Las pruebas deben correr sin ffmpeg, Redis, Whisper ni yt-dlp.
- Los errores del pipeline no son errores HTTP: el `Video` pasa a `failed` con mensaje legible.
- Si falla un recorte, no puede quedar ningún clip parcial del video.

## Goals / Non-Goals

**Goals:**

- Producir clips reales a partir de un archivo de video o de un enlace.
- Mantener los módulos de medios probables de forma aislada con dobles de `subprocess`.
- Dejar el flujo listo para el modelo RNN real: solo cambia `scoring.scorer` cuando existan artefactos.

**Non-Goals:**

- Entrenar o cargar la RNN, traducir al inglés, editar clips o desplegar en Kubernetes.
- Persistir el estado del re-recorte (decisión pendiente en `REFINAMIENTO.md`).

## Decisions

### ADR-01: Dependencias externas con import diferido

**Contexto:** `faster-whisper` y `yt-dlp` son pesados y no hacen falta para la suite de pruebas; ffmpeg es
un binario del sistema.

**Decisión:** importar `faster_whisper` y `yt_dlp` dentro de las funciones que los usan y lanzar
`DependencyMissingError` (subclase de `PipelineError`) con un mensaje legible si no están instalados.
Llamar a `ffmpeg`/`ffprobe` con `subprocess.run(..., shell=False)` y traducir `FileNotFoundError` al mismo
tipo de error.

**Alternativas descartadas:** importar arriba (rompe `manage.py check` y los tests sin dependencias);
usar `shell=True` (riesgo de inyección).

### ADR-02: Ventanas no solapadas alineadas a segmentos

**Contexto:** el spec exige ventanas de 10 a 45 s alineadas a límites de frase, sin decir cómo cubrir el
video.

**Decisión:** se recorre la transcripción acumulando segmentos consecutivos; se cierra la ventana antes de
superar 45 s y solo se emite si dura al menos 10 s. Los segmentos que por sí solos superan 45 s se parten
por palabras, repartiendo el tiempo proporcionalmente al texto. La siguiente ventana empieza en el
segmento donde terminó la anterior (sin solapamiento).

**Alternativas descartadas:** ventanas deslizantes cada 5 s (duplica candidatos y trabajo de recorte);
ventanas por carácter (pierden los límites de frase).

### ADR-03: Selección voraz por puntaje

**Contexto:** el spec fija umbral estricto (> 70), máximo 10 clips, solapamiento máximo del 30 % medido
sobre el intervalo más corto y respaldo de 3 mejores con `tier='medium'`.

**Decisión:** ordenar por puntaje descendente (desempate por inicio) y aceptar una ventana si su
solapamiento con cada aceptada no supera `max_overlap`. Si no se acepta ninguna, repetir con los 3 mejores
puntajes y `tier='medium'`, aplicando el mismo criterio de solapamiento. El puntaje se conserva sin
redondear.

**Alternativas descartadas:** máximo solapamiento sobre la unión (permite duplicados); intervalos de
programación dinámica (sobrecoste para 10 clips).

### ADR-04: Recorte y miniatura en un directorio temporal

**Contexto:** un fallo de ffmpeg no debe dejar clips parciales ni registros.

**Decisión:** la tarea corta todos los mp4 y miniaturas en un `TemporaryDirectory`; solo si todos los
recortes terminan bien crea los `Clip` y copia los archivos al almacén de medios. Si algo falla, borra los
registros creados, sus archivos y el directorio temporal.

**Alternativas descartadas:** guardar cada clip a medida que se corta (deja parciales); cortar en el
almacén definitivo (más difícil de limpiar).

### ADR-05: Traducción fuera de alcance

**Contexto:** el spec pide `text_en` cuando el idioma no es inglés, pero `REFINAMIENTO.md` deja abierta la
herramienta de traducción y qué texto guarda `Clip.text`.

**Decisión:** no traducir en este cambio. Las ventanas usan `text_en` si ya existe y, si no, el texto
original; cuando se decida la herramienta, se añadirá un paso entre `transcribe` y `windows` sin cambiar
contratos.

**Alternativas descartadas:** elegir una librería sin ADR (contradice el proceso del proyecto).

### ADR-06: Límite de tiempo de Celery

**Contexto:** el spec exige un límite configurable y que el video no quede en un estado intermedio.

**Decisión:** `PIPELINE_TIME_LIMIT_S` (por defecto 3600) alimenta `soft_time_limit` y `time_limit`
(`soft + 60`). Al capturar `SoftTimeLimitExceeded` se marca `failed` con mensaje legible.

**Alternativas descartadas:** límite fijo en el código (no configurable); solo `time_limit` (mata el
proceso sin permitir escribir el estado).

## Risks / Trade-offs

- **[Whisper en CPU puede superar los 10 min para 5 min de video]** → modelo `small` configurable con
  `WHISPER_MODEL`; el límite de tiempo evita tareas colgadas.
- **[ffmpeg/ffprobe ausentes en el entorno local]** → error legible `failed` y documentación en README;
  la imagen Docker los instala en un cambio de despliegue.
- **[Dependencias pesadas en requirements]** → import diferido y pruebas con dobles; la instalación de
  Whisper queda documentada como requisito del worker.
- **[Sin traducción]** → se declara en el proposal y en `/modelo/`; el scoring simulado no la necesita.

## Migration Plan

1. Añadir módulos puros y sus pruebas.
2. Reescribir `process_video` y ajustar la prueba existente de la tarea.
3. Añadir variables de entorno y dependencias.
4. Ejecutar `pytest`, `manage.py check` y `openspec validate`.

Rollback: restaurar el cuerpo simulado de `process_video`; los modelos y endpoints no cambian.

## Open Questions

Ninguna que bloquee este cambio. La herramienta de traducción y el estado del re-recorte siguen abiertos
para cambios posteriores.
