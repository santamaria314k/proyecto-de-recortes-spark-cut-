# Informe técnico

El sistema combina Django para la aplicación web, Celery/Redis para tareas largas, Whisper para transcripción, una RNN BiGRU propia para ordenar segmentos y FFmpeg para generar clips. La evaluación del modelo, los datos, métricas y limitaciones están en `EVALUACION_MODELO.md` y en la carpeta `02_modelo`.
