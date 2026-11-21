# Acta de nombre y propuesta de valor

**Producto:** SparkCut  
**Eslogan:** Encuentra el momento que merece ser compartido.  
**Propuesta de valor:** SparkCut recibe un video largo, analiza su transcripción con una RNN propia y entrega los fragmentos textuales más destacados para que el usuario pueda revisarlos, recortarlos y exportarlos como clips.

## Alcance

- Prioriza relevancia relativa dentro del video; no predice viralidad futura.
- Trabaja principalmente sobre el texto transcrito.
- Devuelve puntajes normalizados de 0 a 100 y ventanas candidatas sin solapamiento.
- Integra Django, Celery/Redis, FFmpeg, Docker y Kubernetes.

## Criterio de éxito

En una demostración, el sistema debe mostrar los mejores fragmentos de una conversación o transmisión y permitir al usuario validar y ajustar el inicio y fin del clip.
