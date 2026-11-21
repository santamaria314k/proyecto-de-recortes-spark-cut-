# Design

## Context

Ver `proposal.md` para la motivación. El proyecto parte de `openspec/project.md` y de los 7 specs existentes. No hay código todavía; solo existen la configuración de OpenSpec y la integración con OpenCode.

Restricciones que condicionan el diseño:

- La web nunca procesa video: solo encola tareas y consulta estado.
- Los módulos de IA y video deben ser Python puro, sin dependencia de Django.
- Todo recurso se filtra por usuario; un recurso ajeno responde 404.
- El entorno local es Windows con Python 3.12, Docker disponible y MySQL/Redis vía contenedores.

## Goals / Non-Goals

**Goals:**

- Dejar un proyecto Django 5 ejecutable con las apps y modelos del dominio.
- Separar la configuración por entorno (`.env`) y permitir desarrollo local con Docker Compose.
- Demostrar el flujo web → Redis → worker → MySQL con una tarea simulada.
- Tener pruebas de humo que se ejecuten con `pytest` sin servicios externos obligatorios.

**Non-Goals:**

- Implementar transcripción, scoring real, recorte con ffmpeg o el modelo RNN.
- Completar la interfaz de usuario ni la autenticación social.
- Crear los manifiestos de Kubernetes; se harán cuando el flujo local esté estable.
- Optimizar rendimiento o escalado; el andamiaje prioriza claridad.

## Decisions

### ADR-01: Estructura de apps Django

**Contexto:** el dominio se divide en cuentas, videos, scoring, pipeline y clips.

**Decisión:** crear cinco apps Django (`accounts`, `videos`, `scoring`, `pipeline`, `clips`) y un paquete `sparkcut` para la configuración. Los módulos de IA/video viven en `pipeline/` y `scoring/` como paquetes Python sin imports de Django.

**Alternativas descartadas:** una sola app monolítica (dificulta los límites y las pruebas aisladas); microservicios desde el inicio (sobrecoste para 20 días).

### ADR-02: Configuración por variables de entorno

**Contexto:** MySQL, Redis y secretos cambian entre local y clúster.

**Decisión:** usar `django-environ` o `os.environ` con un `.env.example`; nunca versionar secretos. `DEBUG`, `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `MOCK_SCORER` y `ALLOWED_HOSTS` se leen del entorno.

**Alternativas descartadas:** settings separados por archivo (más duplicación); secretos en el repositorio (inaceptable).

### ADR-03: Celery con tarea simulada

**Contexto:** el flujo asíncrono es central, pero la IA real aún no está lista.

**Decisión:** configurar Celery con Redis y una tarea `process_video` que avance estados (`pending` → `transcribing` → `done`) con `time.sleep` y escriba el progreso en MySQL. La tarea real sustituirá el cuerpo manteniendo la firma.

**Alternativas descartadas:** implementar la IA ahora (bloquea el andamiaje); usar solo tareas síncronas (no valida el flujo real).

### ADR-04: Modelos con validaciones en `clean()` y restricciones de BD

**Contexto:** los estados, rangos y relaciones están definidos en `project.md`.

**Decisión:** modelar `Video`, `Transcript` y `Clip` con `choices`, `CheckConstraint` y validaciones en `clean()`. Los archivos se guardan en `MEDIA_ROOT`; en local se usa un volumen de Docker.

**Alternativas descartadas:** validar solo en formularios (deja pasar datos inválidos por el ORM); usar PostgreSQL (el requisito es MySQL 8).

### ADR-05: Pruebas sin servicios externos por defecto

**Contexto:** el equipo necesita ejecutar pruebas rápido en Windows.

**Decisión:** usar SQLite en memoria para pruebas unitarias y `pytest-django`; las pruebas de integración con MySQL/Redis se marcan y se ejecutan con Docker Compose. Las pruebas de humo no requieren servicios.

**Alternativas descartadas:** exigir MySQL para toda la suite (fricción innecesaria); mockear todo (no valida el ORM).

## Risks / Trade-offs

- **[La tarea simulada no valida la IA real]** → Mantener la firma y los estados; la integración real se prueba en un cambio posterior.
- **[SQLite en pruebas puede ocultar diferencias con MySQL]** → Las pruebas de integración con MySQL se ejecutan en CI y antes de desplegar.
- **[El andamiaje puede crecer demasiado]** → Limitar este cambio a rutas y pantallas mínimas; el resto se hace por cambios pequeños.
- **[Docker en Windows puede ser lento]** → Documentar el arranque con Docker Compose y ofrecer SQLite para pruebas rápidas.

## Migration Plan

1. Crear el proyecto y las apps.
2. Añadir modelos y migraciones iniciales.
3. Configurar Celery y la tarea simulada.
4. Añadir rutas, plantillas y pruebas de humo.
5. Verificar `pytest` y `docker compose config`.
6. Rollback: al ser un proyecto nuevo, basta con eliminar los archivos creados; no hay datos en producción.

## Open Questions

Ninguna que bloquee el andamiaje. Las decisiones pendientes de `REFINAMIENTO.md` (estado del re-recorte, exportación 9:16, traducción, etc.) se resolverán en los cambios que las necesiten.
