# Material de entrenamiento

Esta carpeta contiene los notebooks, scripts, cachés y versiones históricas usadas para entrenar y evaluar SparkCut.

No es necesaria para ejecutar la aplicación web. La aplicación final está en `../proyecto final/`.

Contenido principal:

- `SparkCut_entrenamiento_RNN_v6_final.ipynb`: notebook final de reproducibilidad alineado con el modelo v6 y la aplicación Django. Ejecuta el entrenamiento canónico y valida paridad de artefactos.
- `train_*.py`, `tune_*.py`, `export_*.py`: entrenamiento y evaluación.
- `sparkcut_highlights_v4/`, `sparkcut_highlights_v5/`, `sparkcut_highlights_v6/`: versiones experimentales.
- `model_*.pt`, `tokenizer.model`, `config.json`, `metrics.json`: artefactos históricos de entrenamiento.
- `.hf_cbc_cache/`, `mrhisum_text_data/`: cachés de datasets.
- `sparkcut_django/`: demo de inferencia usada durante los experimentos.

La versión que usa Django está copiada y lista en `../proyecto final/ml_artifacts/`.

El notebook no guarda salidas de error: por defecto inspecciona el modelo existente (`RUN_TRAINING=False`). Para reentrenar, cambia esa variable a `True` en Colab y ejecuta las celdas en orden.
