# Descripción técnica de SparkCut

## Visión y alcance

SparkCut es una plataforma web para descubrir momentos destacados en videos largos. La versión entregada implementa autenticación, carga de videos, transcripción, generación de ventanas, puntuación con un modelo BiGRU/RNN propio, selección de clips, previsualización y exportación.

## Actores

1. Usuario autenticado: carga videos, consulta resultados y edita clips.
2. Worker de procesamiento: ejecuta transcripción, puntuación y recorte.
3. Administrador: configura servicios y despliegue.

## Flujo principal

`subir video -> transcribir -> generar ventanas -> puntuar -> seleccionar top-k -> recortar con FFmpeg -> mostrar clips`

## Requisitos funcionales

- RF01: registrarse/iniciar sesión.
- RF02: cargar un archivo de video o solicitar procesamiento por enlace.
- RF03: mostrar progreso y estado de la tarea.
- RF04: listar clips ordenados por puntaje.
- RF05: ajustar inicio y fin y volver a recortar.
- RF06: consultar la página del modelo con métricas y limitaciones.

## Requisitos no funcionales

- RNF01: ejecución reproducible mediante Docker Compose y Kubernetes.
- RNF02: worker con concurrencia 1 para equipos con 4 GB de RAM.
- RNF03: separación de secretos y configuración por variables de entorno.
- RNF04: pruebas automatizadas y registro de métricas.
