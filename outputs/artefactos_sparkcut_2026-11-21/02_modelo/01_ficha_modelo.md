# Ficha del modelo RNN de SparkCut

**Versión:** contextual ranker v6  
**Tipo:** BiGRU/RNN propia con tokenización SentencePiece y ajuste contextual de posición/duración.  
**Entrada:** segmentos de texto transcrito.  
**Salida:** puntuación relativa normalizada 0–100 para ordenar segmentos del mismo video.

## Evaluación registrada

En un conjunto de prueba separado de 545 videos, la métrica Precision@3 fue **0.3278** frente a **0.2954** de la línea base RNN y **0.2000** de selección aleatoria. Spearman por video fue **0.0626** frente a **0.0502** de la línea base.

## Interpretación

El modelo sirve para priorizar fragmentos relevantes dentro de un video. No afirma que un clip vaya a hacerse viral, porque eso depende del público, distribución y algoritmo de cada red.
