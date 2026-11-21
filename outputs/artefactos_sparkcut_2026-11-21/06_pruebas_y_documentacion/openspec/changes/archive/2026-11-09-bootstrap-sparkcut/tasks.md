# Tasks

## 1. Proyecto y configuración

- [x] 1.1 Crear el proyecto Django `sparkcut` y las apps `accounts`, `videos`, `scoring`, `pipeline` y `clips`; verificar con `python manage.py check`.
- [x] 1.2 Configurar `settings.py` por variables de entorno (`DEBUG`, `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `ALLOWED_HOSTS`, `MOCK_SCORER`) y añadir `.env.example`; verificar que `python manage.py check` funciona sin `.env`.
- [x] 1.3 Añadir `requirements.txt` con Django 5, Celery, Redis, `pytest`, `pytest-django`, `python-dotenv` y `gunicorn`; verificar con `pip install -r requirements.txt`.
- [x] 1.4 Configurar `pytest.ini`/`pyproject.toml` y `conftest.py` para SQLite en memoria; verificar con `pytest --collect-only`.

## 2. Modelos y migraciones

- [x] 2.1 Implementar `Video` con estados, progreso, duración y `source_type`; verificar con una prueba de modelo que crea y valida un video.
- [x] 2.2 Implementar `Transcript` (uno por video, `segments` JSON) y `Clip` (tiempos, puntaje, tier, explicación, `edited`); verificar con pruebas de creación y de restricciones (`start < end`, duración 3–90 s).
- [x] 2.3 Crear migraciones iniciales y verificar con `python manage.py makemigrations --check` y `python manage.py migrate` sobre SQLite.
- [x] 2.4 Añadir pruebas de aislamiento por usuario y de borrado en cascada; verificar con `pytest`.

## 3. Rutas, vistas y plantillas

- [x] 3.1 Implementar `/`, `/dashboard/`, `/videos/new/`, `/videos/<id>/` y `/videos/<id>/status/`; verificar con pruebas de `reverse()` y respuestas 200/404.
- [x] 3.2 Implementar `/modelo/` y `/healthz/`/`/readyz/`; verificar con pruebas de respuesta 200 y JSON.
- [x] 3.3 Añadir plantillas base en español y una pantalla mínima de dashboard/subida; verificar que las vistas renderizan sin error.
- [x] 3.4 Añadir pruebas de que un recurso ajeno responde 404; verificar con `pytest`.

## 4. Celery y flujo asíncrono

- [x] 4.1 Configurar Celery con Redis y la tarea `process_video` simulada; verificar con una prueba que ejecuta la tarea en modo `CELERY_TASK_ALWAYS_EAGER`.
- [x] 4.2 Implementar el endpoint `/videos/<id>/status/` con `{status, progress, error, clips_count}`; verificar con una prueba que simula un video en cada estado.
- [x] 4.3 Documentar el arranque de worker y Redis en `README.md`; verificar que los comandos documentados existen.

## 5. Docker y documentación

- [x] 5.1 Añadir `Dockerfile` y `docker-compose.yml` con MySQL 8 y Redis; verificar con `docker compose config`.
- [x] 5.2 Documentar en `README.md` el arranque local, las pruebas y las variables de entorno; verificar siguiendo los pasos en una copia limpia.
- [x] 5.3 Ejecutar la suite completa (`pytest`) y `python manage.py check`; verificar que todo pasa.

## Workflow follow-up

- Archivar el cambio después de que la suite y `python manage.py check` pasen.
- Verificar que los 7 specs siguen validando con `openspec validate --specs`.
