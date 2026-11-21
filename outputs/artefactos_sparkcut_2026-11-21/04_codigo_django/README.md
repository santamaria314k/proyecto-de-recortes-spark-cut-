# SparkCut

Aplicación web que convierte videos largos en clips cortos con alto potencial viral.

- **Stack:** Django 5 (MVT), MySQL 8, Celery + Redis, faster-whisper, RNN BiGRU propia (PyTorch) y ffmpeg.
- **Arquitectura:** la web nunca procesa video; los workers de Celery hacen el trabajo pesado.
- **Especificaciones:** viven en `openspec/specs/` y el contexto en `openspec/project.md`.

## Requisitos

- Python 3.12+
- Docker Desktop (para MySQL y Redis locales)
- Node.js 22+ solo para las herramientas de OpenSpec/OpenCode
- `ffmpeg` y `ffprobe` en el PATH del worker (extracción de audio, recorte y miniaturas); la imagen Docker ya los incluye
- `faster-whisper` y `yt-dlp` se instalan con `requirements.txt`

Con 4 GB de RAM, usa un solo worker Celery y `WHISPER_MODEL=base` (la configuración de Docker Compose
ya lo deja así). Procesa un video a la vez; la RNN v6 cabe en memoria, pero varios videos simultáneos
pueden agotar la RAM. Si aún falta memoria, cambia temporalmente a `WHISPER_MODEL=tiny` sin cambiar la RNN.

## Arranque local rápido (SQLite)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Abre http://127.0.0.1:8000/.

## Arranque con MySQL y Redis (Docker Compose)

```powershell
docker compose up --build
```

La web queda en http://localhost:8000/. El worker de Celery se inicia como servicio aparte.

Para aplicar migraciones dentro de los contenedores:

```powershell
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py createsuperuser
```

## Pruebas

```powershell
pytest
```

Las pruebas usan SQLite en memoria y no necesitan MySQL ni Redis. El flujo asíncrono se prueba con
`CELERY_TASK_ALWAYS_EAGER=1`.

## Variables de entorno

| Variable | Uso | Valor por defecto |
|---|---|---|
| `DEBUG` | Modo desarrollo | `0` |
| `SECRET_KEY` | Clave de Django | insegura de desarrollo |
| `ALLOWED_HOSTS` | Hosts permitidos | `localhost,127.0.0.1` |
| `DATABASE_URL` | Conexión a BD | `sqlite:///db.sqlite3` |
| `REDIS_URL` | Broker/resultados de Celery | `redis://localhost:6379/0` |
| `CELERY_TASK_ALWAYS_EAGER` | Ejecuta tareas en el proceso web | `0` |
| `MOCK_SCORER` | Usa el scorer simulado (`1`) o el modelo real desde `ml_artifacts/` (`0`) | `0` |
| `WHISPER_MODEL` | Tamaño del modelo de faster-whisper (`tiny`, `base`, `small`, `medium`) | `small` |
| `MAX_VIDEO_DURATION_S` | Duración máxima aceptada por el pipeline | `1200` |
| `MAX_VIDEO_SIZE_MB` | Tamaño máximo de subida | `500` |
| `PIPELINE_TIME_LIMIT_S` | Límite blando de la tarea Celery (el duro es +60 s) | `3600` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Credenciales OAuth 2.0 de Google; si faltan, el botón no aparece | vacío |

En desarrollo usa `MOCK_SCORER=1` si no quieres cargar IA. El modelo real v6 necesita `ml_artifacts/`
(`model_*.pt`, `tokenizer.model`, `config.json`, `metrics.json`, `golden_tests.json` y
`context_ranker.joblib`) y sus dependencias de PyTorch.

## Kubernetes (Kustomize)

```bash
kubectl apply -k k8s/base
```

Incluye Ingress NGINX con límite de 500 MB, `web` (gunicorn + HPA 1–3), `worker` Celery, MySQL 8
StatefulSet, Redis, PVC `media` (RWX), Job de migraciones y ConfigMap/Secret. Los artefactos v6 se
incluyen en la misma imagen Docker para que web y worker carguen siempre el mismo modelo.
Los valores de `k8s/base/secret.yaml` son marcadores: sustitúyelos o gestiona el secreto fuera del repo.

## OpenSpec

```powershell
npx.cmd @fission-ai/openspec list --specs
npx.cmd @fission-ai/openspec validate --specs
npx.cmd @fission-ai/openspec status --change bootstrap-sparkcut
```

La evaluación académica reproducible y la interpretación correcta de las métricas están en
[`docs/EVALUACION_MODELO.md`](docs/EVALUACION_MODELO.md). No se presenta el sistema como predictor de viralidad.

## Estructura

```
sparkcut/        configuración Django y Celery
accounts/        autenticación (Django auth)
videos/          Video, Transcript, subida y estado
scoring/         scorer simulado y página /modelo/
pipeline/        módulos puros de audio, transcripción, ventanas, selección y corte
clips/           Clip, panel y endpoints de media/recorte
templates/       plantillas en español
openspec/        especificaciones y cambios
```

## Estado

Implementado: registro y acceso con correo, login con Google (allauth), carga por archivo o enlace con
validaciones de formato/tamaño/SSRF/duración, pipeline completo (descarga, audio, transcripción, ventanas,
puntaje, selección y recorte), panel de clips con reproductor (Range), editor de tijera, restaurar IA,
descarga/borrado con limpieza de archivos, páginas de error en español y despliegue en Kubernetes.

La transcripción conserva el texto original y, si el idioma no es inglés, añade `text_en` con la pasada
`task="translate"` de Whisper (sin servicios externos). Las ventanas puntúan con `text_en` y muestran el
texto original en los clips; `/modelo/probar/` puntúa texto en inglés.

El contenedor incluye los artefactos v6 de la RNN propia y Docker/Kubernetes ejecutan `MOCK_SCORER=0`.
Pendiente: exportación vertical 9:16.
