# Protocolo de validación ligera

1. Seleccionar tres videos de prueba con transcripción clara.
2. Ejecutar el pipeline con `MOCK_SCORER=0`.
3. Revisar los tres clips principales por video.
4. Registrar si el momento seleccionado es más relevante que el contexto inmediato.
5. Guardar duración, puntaje, texto y observación en una bitácora.

La evaluación cuantitativa oficial se conserva en `02_modelo/metrics.json` y la evaluación técnica completa en `06_pruebas_y_documentacion/EVALUACION_MODELO.md`.
