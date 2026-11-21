# Modelo de datos y convenciones

## Entidades principales

- `Video`: archivo, propietario, estado de procesamiento y duración.
- `Transcript`: segmentos transcritos con tiempo inicial y final.
- `Clip`: ventana seleccionada, puntaje, texto y archivo recortado.
- `Task`: estado y progreso del procesamiento asíncrono.

## Convenciones

- Python: `snake_case`; clases Django: `PascalCase`.
- API y rutas: nombres en minúsculas con guiones.
- Puntajes persistidos en escala 0–100; el modelo interno puede trabajar en 0–1.
- Los archivos grandes se guardan en media/PVC, no en Git.
