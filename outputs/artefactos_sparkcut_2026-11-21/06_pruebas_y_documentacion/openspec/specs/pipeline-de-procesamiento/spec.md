# Pipeline de procesamiento

## Purpose

Tarea asíncrona (worker Celery) que convierte un video aceptado en clips puntuados: descarga (si es enlace),
validación de duración, extracción de audio, transcripción con marcas de tiempo, traducción al inglés si
corresponde, generación de ventanas candidatas, puntuación con la RNN propia, selección de fragmentos y
recorte con ffmpeg. La petición web nunca bloquea: el trabajo pesado corre en el worker. También define
el manejo de fallos y su registro.
Satisface RF-07..RF-13, RNF-01, RNF-02, RNF-12 y el caso de uso CU-03.

## Requirements

### Requirement: Procesamiento fuera de la petición web
El sistema SHALL ejecutar todo trabajo pesado (descarga, audio, transcripción, IA, recorte) en workers
Celery, nunca en la petición web (RNF-01, RNF-02).

#### Scenario: Encolado inmediato
- **WHEN** el usuario crea un video
- **THEN** la web encola la tarea `process_video` y responde de inmediato sin esperar al procesamiento

#### Scenario: Video de 5 minutos en CPU
- **WHEN** se procesa un video de 5 minutos en CPU con el ensamble de producción
- **THEN** el objetivo es terminar en menos de 10 minutos

### Requirement: Actualizar estado y progreso por fase
El sistema SHALL actualizar `status` y `progress` del `Video` al iniciar cada fase, según la tabla de
estados definida en `gestion-de-videos`.

#### Scenario: Cambio de fase
- **WHEN** el worker inicia la fase de transcripción
- **THEN** el `Video` queda en `transcribing` con `progress` 40 antes de empezar el trabajo de esa fase

### Requirement: Extraer el audio del video
El sistema SHALL extraer el audio del video con ffmpeg antes de transcribir.

#### Scenario: Video sin pista de audio
- **WHEN** el archivo no contiene ninguna pista de audio
- **THEN** el video queda en `failed` con un mensaje legible que indica que no se encontró audio

### Requirement: Transcribir el audio con marcas de tiempo
El sistema SHALL transcribir el audio (faster-whisper en CPU, int8) y guardar una transcripción con
segmentos ordenados `{start, end, text}` en la columna JSON de `Transcript` (MoSCoW: Must — RF-07).

#### Scenario: Transcripción correcta
- **WHEN** el worker transcribe un video con voz
- **THEN** guarda un `Transcript` (único por video) con `language` detectado y segmentos ordenados por `start`

#### Scenario: Video sin voz
- **WHEN** el audio no contiene voz o la transcripción resulta vacía
- **THEN** el video queda en `failed` con un mensaje legible y la traza técnica queda en el log del worker

### Requirement: Detectar idioma y traducir al inglés
El sistema SHALL detectar el idioma y, si no es inglés, traducir el texto al inglés para puntuar
(MoSCoW: Should — RF-08).

#### Scenario: Video en español
- **WHEN** la transcripción detecta que el idioma es español
- **THEN** cada segmento guarda además `text_en` para el modelo de puntuación

#### Scenario: Video en inglés
- **WHEN** la transcripción detecta que el idioma es inglés
- **THEN** no se traduce y los segmentos no incluyen `text_en`

### Requirement: Generar ventanas candidatas
El sistema SHALL generar ventanas candidatas entre 10 y 45 segundos, alineadas a límites de frase,
sin ninguna ventana fuera del rango configurado (MoSCoW: Must — RF-09).

#### Scenario: Ventanas alineadas
- **WHEN** el worker genera las ventanas a partir de la transcripción en inglés
- **THEN** cada `Window {start, end, text}` dura entre 10 y 45 s y coincide con límites de frase

#### Scenario: Sin ventanas válidas
- **WHEN** la transcripción es demasiado corta para formar al menos una ventana de 10 s
- **THEN** el video queda en `failed` con un mensaje legible que indica que no hay voz suficiente para generar fragmentos

### Requirement: Puntuar cada ventana con la RNN propia
El sistema SHALL puntuar cada ventana entre 10 y 100 con la RNN propia mediante `score_segments(texts)`,
que devuelve un valor por texto en el mismo orden de entrada (MoSCoW: Must — RF-10).

#### Scenario: Inferencia en lote
- **WHEN** `score_segments` recibe la lista de textos de las ventanas
- **THEN** devuelve una lista de floats entre 10.0 y 100.0, del mismo tamaño y orden

### Requirement: Seleccionar fragmentos con umbral 70 y sin solapamientos
El sistema SHALL seleccionar solo ventanas con puntaje mayor a 70, sin solapamientos mayores al 30 %,
mediante `select_clips(windows, scores, threshold=70, max_clips=10, max_overlap=0.30)`
(MoSCoW: Must — RF-11). El solapamiento se mide como la fracción del intervalo más corto de las dos
ventanas que queda cubierta por la otra, y la selección recorre las ventanas de mayor a menor puntaje.

#### Scenario: Selección válida
- **WHEN** existen varias ventanas con puntaje mayor a 70 que se solapan
- **THEN** los clips guardados superan 70, no se solapan más del 30 % y se conservan los de mayor puntaje

#### Scenario: Más candidatos que el máximo
- **WHEN** hay más de 10 ventanas válidas
- **THEN** se guardan como máximo 10 clips con `tier='high'`, los de mayor puntaje

#### Scenario: Puntaje exactamente en el umbral
- **WHEN** una ventana puntúa exactamente 70.0
- **THEN** no es seleccionable como `high`

### Requirement: Respaldo cuando ninguno supera el umbral
El sistema SHALL, cuando ningún fragmento supera 70, guardar los 3 mejores puntajes, también sin
solapamientos mayores al 30 %, para mostrarlos como «potencial medio» diferenciado
(MoSCoW: Should — RF-12).

#### Scenario: Ninguno supera 70
- **WHEN** el puntaje máximo del video es menor o igual que 70
- **THEN** se guardan los 3 mejores clips con `tier='medium'` y se muestran diferenciados como potencial medio

#### Scenario: Menos de tres candidatos
- **WHEN** existen menos de 3 ventanas válidas y ninguna supera 70
- **THEN** se guardan todas las disponibles con `tier='medium'`

### Requirement: Recortar con precisión de fotograma
El sistema SHALL recortar cada fragmento con ffmpeg con precisión de fotograma, lo que implica
recodificar el segmento, y SHALL generar su miniatura (MoSCoW: Must — RF-13).

#### Scenario: Recorte exacto
- **WHEN** el worker ejecuta `cut_clip(src, start, end, out)` para un clip seleccionado
- **THEN** la duración del mp4 coincide con el intervalo (±0.2 s) y se genera miniatura

### Requirement: Manejo y registro de fallos del pipeline
El sistema SHALL llevar el video a `failed` ante cualquier error del pipeline (incluido el fallo de
ffmpeg al recortar cualquier clip), mostrar solo un mensaje legible en `Video.error`, registrar la traza
completa en el log del worker, eliminar los archivos temporales y SHALL imponer un límite de tiempo
configurable a la tarea (RNF-12).

#### Scenario: Fallo interno del pipeline
- **WHEN** una etapa del pipeline falla durante el procesamiento
- **THEN** el video queda en `failed` con mensaje legible, el detalle técnico completo queda en el log del worker y no quedan archivos temporales

#### Scenario: Fallo al recortar un clip
- **WHEN** ffmpeg falla al recortar uno de los clips seleccionados
- **THEN** el video queda en `failed` y no queda ningún clip parcial guardado para ese video

#### Scenario: Tiempo límite excedido
- **WHEN** la tarea supera el límite de tiempo configurado
- **THEN** el video queda en `failed` con un mensaje legible y no permanece en un estado intermedio
