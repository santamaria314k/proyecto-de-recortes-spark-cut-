# Proposal

## Why

SparkCut ya tiene sus 7 especificaciones y el contexto del proyecto, pero todavía no existe código ejecutable. Sin un esqueleto Django verificable no se pueden implementar los requisitos ni validar los contratos entre la web, los workers y los módulos puros de IA/video.

Este cambio crea la base mínima ejecutable para empezar a trabajar por iteraciones pequeñas, sin adelantar la implementación completa de ningún requisito.

## What Changes

- Crear el proyecto Django 5 `sparkcut` con configuración por variables de entorno.
- Crear las apps `accounts`, `videos`, `scoring`, `pipeline` y `clips` con su estructura mínima.
- Definir los modelos `Video`, `Transcript` y `Clip` con los campos, estados y validaciones descritos en `project.md`.
- Configurar Celery + Redis y una tarea `process_video` simulada (sin IA real) para probar el flujo asíncrono.
- Exponer las rutas base: `/`, `/dashboard/`, `/videos/new/`, `/videos/<id>/`, `/videos/<id>/status/`, `/modelo/`, `/healthz/` y `/readyz/`.
- Añadir plantillas base y una interfaz mínima en español.
- Añadir `docker-compose.yml` para MySQL 8 y Redis locales, más un `Dockerfile` para web/worker.
- Configurar `pytest` + `pytest-django` con pruebas de humo para modelos, rutas y salud.
- Documentar el arranque local en `README.md`.

**Fuera de alcance de este cambio:** transcripción real, modelo RNN, recorte con ffmpeg, editor de clips, exportación 9:16, autenticación con Google, manifiestos de Kubernetes y la página pública completa del modelo. Todo eso se implementará en cambios posteriores sobre esta base.

## Capabilities

### New Capabilities

Ninguna. Este cambio no introduce comportamiento nuevo: implementa la base para los requisitos ya definidos en `openspec/specs/`.

### Modified Capabilities

Ninguna. Los 7 specs existentes no cambian; el andamiaje debe cumplirlos.

> El cambio declara `skip_specs: true` porque es una implementación inicial sin delta de comportamiento.

## Impact

- **Código:** se crea la estructura del proyecto Django, apps, modelos, rutas, plantillas y tareas Celery.
- **Dependencias:** Django 5, Celery, Redis, MySQL (cliente), `pytest`, `pytest-django`, `python-dotenv` y `gunicorn`.
- **Infraestructura local:** `docker-compose.yml` con MySQL 8 y Redis; `Dockerfile` para web y worker.
- **Contratos:** no cambian los módulos Python, endpoints ni artefactos del modelo definidos en `project.md`; el andamiaje los respeta y deja los puntos de extensión.
- **Riesgo:** el flujo asíncrono se prueba con una tarea simulada; la integración real con IA y ffmpeg queda para cambios posteriores.
