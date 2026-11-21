# Integración de SparkCut con Django

Este paquete expone por HTTP el ensamble BiGRU que está en la carpeta raíz junto a `config.json`, `tokenizer.model` y `model_0.pt`–`model_2.pt`.

## Objetivo correcto: destacar dentro del video

SparkCut ordena ventanas del mismo video por potencial de ser un momento destacado. **No intenta predecir si el corto se volverá viral**; eso depende de distribución, audiencia y plataforma. El puntaje de la API es un percentil relativo frente a otras ventanas del video, no una probabilidad.

Los pesos originales se entrenaron con la transcripción y marcadores temporizados de repetición de Content Behavior Corpus. En la prueba oficial de 545 videos, el modelo transcript-only obtuvo precision@3 0,295, frente a 0,20 al azar; Spearman por video 0,050 y AUC 0,554. Eso muestra una señal útil pero modesta.

Los datos de entrenamiento disponibles son en inglés. El rendimiento con transcripciones en español, como videos de creadores colombianos, todavía no está medido. Los pesos originales tampoco interpretan imágenes o audio directamente.

## Instalación

Instala `sparkcut_django/requirements.txt` en el entorno de Django. En `settings.py` agrega `sparkcut_django.apps.SparkCutConfig` a `INSTALLED_APPS`.

En el `urls.py` del proyecto:

```python
from django.urls import include, path

urlpatterns = [
    # ... tus rutas existentes ...
    path("api/sparkcut/", include("sparkcut_django.urls")),
]
```

Por defecto, los artefactos se buscan en la carpeta raíz de este proyecto. En despliegue, apunta `SPARKCUT_MODEL_DIR` a la carpeta que contiene los cinco artefactos; opcionalmente define `SPARKCUT_DEVICE=cpu` para forzar CPU. El modelo se carga una vez por proceso Django, al llegar la primera puntuación.

## Endpoint

`POST /api/sparkcut/score/` con `Content-Type: application/json`:

```json
{
  "max_clips": 5,
  "segments": [
    {"start": 0.0, "end": 4.2, "text": "First part of the transcript."},
    {"start": 4.2, "end": 8.7, "text": "More transcript words go here."}
  ]
}
```

La app debe enviar segmentos ASR con tiempos en segundos. El servicio forma ventanas solapadas de 10–45 segundos con un objetivo de 25 segundos y salto de 8 segundos, puntúa y devuelve las de mayor puntuación. La respuesta incluye `start`, `end`, `text` y `score`; en v6 también muestra `text_rank`, `tfidf_rank` y `novelty_rank`. `/api/sparkcut/health/` es una comprobación básica del servicio.

El endpoint no descarga ni procesa el video: conecta aquí el resultado de tu transcriptor ASR. Como el modelo actual se entrenó con texto en inglés, sus puntuaciones para otros idiomas no están validadas.

## Experimento de ranking por video

`train_highlight_ranker.py` usa replay por ventana, marca los picos respecto a las demás ventanas del mismo video y entrena una pérdida pairwise. También prueba descripciones de escena, acciones y OCR. La prueba sigue separando videos completos.

Ese ajuste **no superó los pesos originales**: precision@3 0,292 frente a 0,295 y AUC 0,545 frente a 0,554 en la evaluación de transcripción. Al añadir descripciones visuales, quedó en 0,275 de precision@3. Por tanto `sparkcut_highlights_v4/config.json` lleva `production_ready: false`; conserva los pesos originales como la mejor opción disponible. Los resultados detallados están en `sparkcut_highlights_v4/metrics.json`.

El corpus de repetición tiene señales por segmento, pero se compone de videos en inglés. Para una mejora fiable con videos colombianos hacen falta ejemplos en español. Las descripciones visuales no mejoraron la prueba actual.

## Variante v5

`sparkcut_highlights_v5/` combina el ranking textual del RNN (70%) con una señal de posición dentro del video (30%), elegida usando validación. En la prueba reservada obtuvo precision@3 0,300 y Spearman 0,084. Se conserva como comparación histórica.

## Variante v6: texto y cambio entre segmentos

`sparkcut_highlights_v6/` conserva el ensamble RNN y añade un ranker TF-IDF entrenado con 33.659 ventanas transcriptas. Dentro de cada video mezcla el puesto del RNN (30%), el puesto TF-IDF (20%) y la novedad textual respecto a la ventana siguiente (50%). Los pesos se seleccionaron usando 549 videos de validación; el conjunto oficial de prueba permaneció aparte.

En los 545 videos de prueba, precision@3 fue **0,328**, frente a **0,295** para el ensamble RNN sin el nuevo ranker y **0,200** al azar. Spearman por video fue **0,063**, frente a **0,050** para el RNN solo. Precision@3 significa la fracción de las tres ventanas sugeridas que cae en el quintil superior de repetición; no es una probabilidad de viralidad. La mejora en esta métrica fue de 3,2 puntos porcentuales, pero la correlación global sigue siendo baja.

Para cargar v6, apunta `SPARKCUT_MODEL_DIR` a `sparkcut_highlights_v6/`. Incluye `context_ranker.joblib`, así que despliega la carpeta completa. La configuración sigue con `production_ready: false`: las etiquetas de repetición son una aproximación a momentos destacados, y el rendimiento con transcripciones traducidas al español aún no se ha medido.

La base Mr. HiSum encontrada contiene características textuales por segundo para unos 30.000 videos, pero su archivo de texto pesa 18,9 GB y la descarga fue demasiado lenta en este equipo. No se descargó ni se usó para entrenar v6; el paquete exportado no incluye esos datos.
