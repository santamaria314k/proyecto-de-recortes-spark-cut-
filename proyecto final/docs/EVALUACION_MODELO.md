# Evaluación académica del modelo de selección de cortos

## Qué resuelve

El sistema ordena ventanas de transcripción para encontrar momentos que sobresalen dentro de un video largo. No predice si una publicación será viral: las vistas, la audiencia y el algoritmo de cada red social quedan fuera del modelo.

## Protocolo usado

- Fuente: Content Behavior Corpus, con marcas temporales de repetición de YouTube.
- División por video completo: ningún video de prueba participa en el entrenamiento ni en la selección de pesos.
- Entrenamiento: 33.659 ventanas de 5.257 videos.
- Validación: 549 videos.
- Prueba final reservada: 545 videos.
- Modelo: ensamble de tres BiGRU bidireccionales con atención; v6 añade TF-IDF y cambio textual entre ventanas.
- Idioma evaluado: inglés.

## Resultado en la prueba reservada

| Sistema | Precision@3 | Spearman por video |
|---|---:|---:|
| Selección aleatoria | 0,200 | — |
| RNN base | 0,295 | 0,050 |
| SparkCut v6 | **0,328** | **0,063** |

`Precision@3` es la fracción media de las tres ventanas seleccionadas que pertenece al 20 % superior de repetición de su video. Es una métrica de ranking por video, no una probabilidad de viralidad.

## Lectura correcta

La v6 mejora al azar y supera a la RNN base en el conjunto de prueba reservado. La señal es útil para priorizar revisión humana, pero la magnitud no permite afirmar precisión alta ni garantía de viralidad. La etiqueta de repetición es un proxy de momento destacado, no una anotación humana directa de relevancia textual.

## Limitaciones que deben declararse

1. El entrenamiento y la prueba principal están en inglés; el flujo en español depende de la traducción de Whisper y todavía requiere una prueba separada.
2. El modelo usa texto; no detectará un momento visual que no tenga una señal relevante en la transcripción.
3. Todavía no se han calculado intervalos de confianza bootstrap ni un conjunto manual colombiano. No deben inventarse para la exposición.
4. El resultado mide relevancia relativa dentro de cada video, no éxito futuro en TikTok, YouTube Shorts o Instagram.

## Frase recomendada para la defensa

> “SparkCut es un sistema de ranking de ventanas textuales. En 545 videos no vistos, sus tres primeras sugerencias alcanzaron el 32,8 % de coincidencia con ventanas del 20 % superior de repetición, frente al 20 % aleatorio. Por eso lo presentamos como asistencia para encontrar momentos destacados, no como predictor de viralidad.”

Los números publicados en esta página deben coincidir con `ml_artifacts/metrics.json`.
