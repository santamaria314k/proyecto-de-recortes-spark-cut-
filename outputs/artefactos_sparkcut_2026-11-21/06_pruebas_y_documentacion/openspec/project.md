# SparkCut — Contexto del proyecto

Aplicación web (Django 5 + MySQL 8 + Celery/Redis, desplegada en Kubernetes) que convierte videos largos
en fragmentos cortos con alto potencial viral, usando transcripción automática y una RNN de autoría propia.

## Visión y objetivo

- Ser la herramienta de referencia para convertir videos largos en clips con alto potencial de atención,
  combinando transcripción automática, un modelo de lenguaje propio y control editorial del usuario.
- A partir de un video: detectar, puntuar de 10 a 100 y recortar automáticamente los fragmentos con mayor
  potencial viral (RNN BiGRU con atención, PyTorch, entrenada en Colab con datasets de Hugging Face).

## Alcance

**Incluye:** registro/login (correo y Google OAuth), subida por archivo o enlace, transcripción,
puntuación 10–100, recorte automático, panel de clips con previsualización, editor de recorte (tijera),
restaurar recorte IA, descarga/eliminación, exportación vertical 9:16 y subtítulos (opcionales),
página pública «Cómo funciona el modelo», despliegue en Kubernetes.

**Fuera de alcance:** publicación automática en redes, edición avanzada (efectos/transiciones/múltiples pistas),
análisis de imagen o audio como señal del modelo, pagos/suscripciones, app móvil nativa,
transmisiones en vivo, alta disponibilidad multirregión.

## Restricciones y supuestos

- Tiempo: 20 días calendario (30/10/2026 – 18/11/2026), equipo de 2 personas (Kevin y Andrés).
- Videos de hasta **20 minutos (1200 s)** y **500 MB** por archivo.
- Descarga por enlace (yt-dlp) puede fallar por bloqueos: la subida de archivo local es el flujo principal.
- Legal: el usuario debe tener derechos sobre el contenido; la interfaz muestra un aviso.
- El puntaje ordena momentos destacados dentro del video; no predice ni garantiza viralidad en redes.

## Arquitectura

- **Monolito modular Django (MVT)** con procesamiento asíncrono por workers; desplegado en Kubernetes.
  - La web **nunca** procesa video: encola la tarea en Redis y responde.
  - El worker consume, actualiza estado en MySQL y escribe clips en un volumen compartido.
- **Decisiones (ADR):**
  - ADR-01: Django 5 con MVT (requisito de la materia; ORM, auth y admin incluidos).
  - ADR-02: MySQL 8 utf8mb4 (transacciones ACID y columnas JSON para transcripciones).
  - ADR-03: Celery + Redis para tareas asíncronas (procesamiento de minutos, escalable por workers).
  - ADR-04: faster-whisper en CPU (int8) — local, sin costo, marcas de tiempo por palabra.
  - ADR-05: RNN propia BiGRU con atención en PyTorch, entrenada en Colab (requisito de autoría).
  - ADR-06: ffmpeg para recorte y miniaturas (precisión de fotograma, rendimiento).
  - ADR-07: django-allauth para Google y correo.
  - ADR-08: Docker + Kubernetes con Kustomize (kind/minikube en local).
  - ADR-09: Templates de Django + JS sin framework (respeta MVT, sin SPA/React).

### Apps Django y módulos

| App | Models | Views/Vistas | Templates | Módulos de servicio |
|---|---|---|---|---|
| accounts | Usuario (auth) y cuentas sociales | Login, registro, logout | `accounts/*.html` | — |
| videos | `Video`, `Transcript` | Subida, detalle, estado (JSON), eliminación | `videos/*.html` | Tarea `process_video` |
| scoring | — | `/modelo/` y probador | `model/*.html` | `scorer` (carga RNN, `score_segments`) |
| pipeline | — | — | — | `download`, `audio`, `transcribe`, `windows`, `select`, `cut` |
| clips | `Clip` | Panel, edición (trim), descarga, media con Range | `clips/*.html`, `editor.js` | Tarea `recut_clip` |

Los módulos de IA y video son **Python puro sin dependencia de Django** para poder probarlos de forma aislada;
solo la tarea principal y la persistencia usan el ORM.

### Despliegue en Kubernetes

Ingress NGINX (límite 500 MB) · `web` Deployment+Service+HPA (gunicorn, 1–3 réplicas) · `worker` Deployment
(Celery, escala con `kubectl scale`) · `mysql` StatefulSet+PVC · `redis` Deployment · `media` PVC compartido ·
Job `migrate` · ConfigMap/Secret (nunca secretos en el repo) · sondas `/healthz/` y `/readyz/` (readiness verifica BD).

## Modelo de datos (MySQL 8, 4 entidades)

- **Video**: `id`, `user_id` (FK CASCADE), `title`, `source_type` ENUM('upload','url'), `source_url`, `file`,
  `status` ENUM de 7 estados, `progress` (0–100), `error` TEXT, `duration_s` (≤ 1200), `created_at`.
- **Transcript**: `id`, `video_id` (FK única, CASCADE, una por video), `language`, `segments` JSON
  (lista de `{start, end, text}` y `text_en` si hubo traducción), `created_at`.
- **Clip**: `id`, `video_id` (FK CASCADE), `start_time`, `end_time` (`start < end`), `orig_start_time`,
  `orig_end_time` (límites propuestos por la IA, para «Restaurar IA»), `score` (10–100), `tier` ENUM('high','medium'),
  `text`, `file`, `thumbnail`, `explanation` JSON (emociones y dimensiones), `edited` BOOL, `created_at`.
- **Usuario**: gestionado por Django auth + allauth (sesiones Google OAuth y correo/contraseña).

**Estados del video:** `pending`(0) → `downloading`(10) → `transcribing`(40) → `scoring`(70) →
`clipping`(90) → `done`(100); `failed` posible desde cualquier estado (mensaje legible en `error`).

**Reglas de integridad:**
- Borrar un Video elimina Transcript, Clips (CASCADE) y también los archivos asociados.
- Toda consulta filtra por `user_id`; un recurso ajeno responde 404.
- Índices: `(user_id, created_at)` en Video, `(video_id, score)` en Clip, único `video_id` en Transcript.
- Validaciones: `0 ≤ progress ≤ 100`, `start_time < end_time`, duración de clip entre **3 y 90 s**.
- Charset `utf8mb4` con collation `utf8mb4_unicode_ci`.
- DDL de referencia: `docs/database/schema.sql` (migraciones generadas por el ORM de Django).

## Contratos de datos e interfaces

Cualquier cambio de contrato se acuerda entre Kevin y Andrés y se actualiza primero en la especificación del cambio (OpenSpec).

### Módulos Python

| Estructura / función | Definición | Productor | Consumidor |
|---|---|---|---|
| `Segment` | `{start: float, end: float, text: str, text_en?: str}` en segundos | `transcribe` | `windows` |
| `Window` | `{start, end, text}` entre 10 y 45 s, alineada a límites de frase | `windows` | `scorer`, `select` |
| `score_segments` | `score_segments(texts: list[str]) -> list[float]` (10.0–100.0, mismo orden) | `scoring.scorer` | `select` |
| `score_segments_detailed` | `{score, dims: {hook, emotion, surprise, conflict, story}, top_emotions: [(nombre, prob)]}` | `scoring.scorer` | `select`, vistas |
| `score_segments_contextual_detailed` | Lista detallada con ranking relativo RNN + TF-IDF + cambio textual para todas las ventanas de un video | `scoring.scorer` | tarea `process_video` |
| `select_clips` | `select_clips(windows, scores, threshold=70, max_clips=10, max_overlap=0.30) -> list[ClipSpec]` | `select` | tarea `process_video` |
| `ClipSpec` | `{start, end, score, tier, text, explanation}` | `select` | `cut`, ORM |
| `cut_clip` | `cut_clip(src, start, end, out) -> Path` con precisión de fotograma | `cut` | `process_video`, `recut_clip` |

La versión actual del modelo puntúa **solo con el texto**. El pipeline usa el ranker contextual únicamente
cuando dispone de la lista completa de ventanas del mismo video; no usa la posición temporal, imagen ni audio.

### Endpoints HTTP

Todos requieren sesión iniciada, salvo `/`, `/accounts/*`, `/modelo/` y las sondas de salud.

| Método | Ruta | Función | Respuesta |
|---|---|---|---|
| GET | `/dashboard/` | Lista de videos del usuario | HTML |
| GET, POST | `/videos/new/` | Formulario de archivo o enlace | HTML; redirige al detalle |
| GET | `/videos/<id>/` | Detalle y progreso | HTML |
| GET | `/videos/<id>/status/` | Sondeo cada 2 s | JSON `{status, progress, error, clips_count}` |
| POST | `/videos/<id>/delete/` | Elimina video, clips y archivos | Redirección |
| GET | `/videos/<id>/clips/` | Panel de clips ordenado por puntaje | HTML |
| GET | `/clips/<id>/media/` | Reproduce el clip (soporte Range) | 206 Partial Content con cabecera `Range`; 200 sin ella; 416 si el rango es inválido |
| GET | `/clips/<id>/download/` | Descarga del mp4 | Archivo adjunto |
| POST | `/clips/<id>/trim/` | Nuevos límites `{start, end}` | 202 si válido; 400 si no |
| GET | `/clips/<id>/status/` | Estado del re-recorte | JSON `{status}` (`processing`, `ready` o `failed`) |
| POST | `/clips/<id>/restore/` | Vuelve al recorte original de la IA | JSON |
| POST | `/clips/<id>/delete/` | Elimina un clip | Redirección |
| GET | `/modelo/` | Descripción y métricas del modelo | HTML |
| POST | `/modelo/probar/` | Puntaje de un texto (hasta 500 caracteres) | JSON |
| GET | `/healthz/`, `/readyz/` | Liveness y readiness | 200 o 503 |

**Pendiente de contrato:** el endpoint de exportación vertical 9:16 (RF-20, Could) aún no está definido; debe acordarse y registrarse aquí antes de implementarlo. Las rutas no autenticadas se redirigen al login (HTML) o responden 403 (JSON).

**Manejo de errores:** 400 entrada inválida (JSON `{error, code}` en español) · 403 CSRF/permisos ·
404 inexistente o ajeno · 413 archivo > 500 MB · 500 genérico (detalle al log).
Los fallos del procesamiento **no** son errores HTTP: el Video pasa a `failed` con mensaje legible
y la traza técnica queda en el log del worker.

## Contrato de los artefactos del modelo

El entrenamiento en Colab entrega una carpeta `ml_artifacts/` que la aplicación carga al iniciar:

| Archivo | Contenido |
|---|---|
| `model_0.pt` … `model_N.pt` | Pesos (state_dict) de cada RNN del ensamble |
| `tokenizer.model` | Tokenizador SentencePiece propio |
| `config.json` | Versión, hiperparámetros, nombres de emociones, pesos del puntaje, calibración y parámetros de ventana |
| `metrics.json` | Resultados de evaluación que muestra `/modelo/` |
| `golden_tests.json` | Textos con puntaje esperado (verificación de que la app reproduce el entrenamiento) |
| `context_ranker.joblib` | Ranker TF-IDF v6 usado para ordenar ventanas dentro de un video completo |

Si falta un archivo, el worker no inicia y el mensaje indica cuál falta. Con `MOCK_SCORER=1` se usa un
puntaje simulado determinista para desarrollar sin el modelo.

## Componente de IA (v6)

- **Modelo:** RNN BiGRU con atención, de autoría propia; tokenizador SentencePiece unigram propio (12 000 piezas).
  Embedding 192, BiGRU de 2 capas con 160 unidades por dirección, atención sobre la secuencia,
  dropout 0.4 y word dropout 10 %. Ensamble de 3 modelos con semillas distintas (se promedian salidas).
- **Entrada:** texto; si el idioma es otro, Whisper lo traduce al inglés antes de puntuar. No recibe imagen ni audio.
- **Puntaje:** la RNN combina `adj` y `pk` con los pesos y calibración de `config.json`. Para el video completo,
  el ranker contextual mezcla RNN (30 %), TF-IDF (20 %) y cambio textual hacia la ventana siguiente (50 %).
  Umbral de selección: **> 70**.
- **Datos:** `behavior-in-the-wild/content-behavior-corpus` (repetición de YouTube), `google-research-datasets/go_emotions`
  y `dair-ai/emotion` (tareas auxiliares de emoción), ~6 200 ventanas etiquetadas por un LLM profesor con rúbrica
  (gancho, emoción, sorpresa, conflicto, historia — destilación), y 250 ventanas de test etiquetadas manualmente
  por Kevin y Andrés.
- **Evaluación:** repetición des-sesgada (Spearman, precisión@3, AUC), estabilidad entre semillas,
  independencia de la posición, fidelidad al profesor, prueba de sensatez y comparación con humanos;
  con intervalos de confianza del 95 % por bootstrap. Resultados en `metrics.json`, publicados en `/modelo/`.
- **Limitaciones declaradas:** se entrenó principalmente con texto en inglés y etiquetas de repetición de YouTube;
  el puntaje estima relevancia relativa, no garantiza viralidad, y no usa audio ni imagen como señal.
- Historial: v1 solo emociones (descartada), v2 dependía de la posición (corregida en v3: solo texto,
  objetivo des-sesgado y profesor LLM con rúbrica).

## Requisitos no funcionales (resumen)

- **Rendimiento:** nada pesado en la petición web (todo en workers Celery); video de 5 min en CPU < 10 min.
- **Escalabilidad:** workers escalan horizontalmente con `kubectl scale`.
- **Seguridad:** aislamiento por usuario (404 de recursos ajenos), secretos solo por variables de entorno/Secrets,
  protección CSRF, validación de formato/tamaño/duración, `subprocess` sin shell.
- **Disponibilidad:** volúmenes persistentes y sondas de salud con reinicio automático.
- **Mantenibilidad:** módulos puros testeables; cobertura objetivo 70 % en pipeline, scoring y clips.
- **Portabilidad:** una imagen Docker para web y worker; misma configuración en local y en el clúster.
- **Reproducibilidad:** semillas fijas, configuración versionada y métricas guardadas.
- **Usabilidad:** interfaz responsiva en español (escritorio y móvil).

## Casos de uso

CU-01 Autenticarse · CU-02 Cargar un video · CU-03 Procesar video y generar clips (sistema/worker) ·
CU-04 Revisar clips en el panel · CU-05 Ajustar un clip con la tijera · CU-06 Descargar o eliminar ·
CU-07 Consultar cómo funciona el modelo · CU-08 Administrar usuarios (admin Django).

## Convenciones

- Idioma del producto y de los mensajes de interfaz: español (interfaz responsiva en español).
- Idioma de los artefactos OpenSpec: español, manteniendo encabezados estructurales y palabras clave SHALL/MUST en inglés.
- Documentos fuente del proyecto: descripción del sistema, diagramas C4 (N1 contexto / N2 contenedores /
  N3 componentes del worker / secuencia) y modelo de datos con convenciones.
- Repositorio: https://github.com/santamaria314k/proyecto-de-recortes-spark-cut-
- Calidad: `pytest` + `pytest-django` y GitHub Actions.
- Los contratos (módulos Python, endpoints, artefactos del modelo) se actualizan primero en OpenSpec antes de codificar.
