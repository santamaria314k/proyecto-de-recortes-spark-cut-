# Gestión de videos

## Purpose

Carga y ciclo de vida de los videos del usuario: subida de archivo local (flujo principal), carga mediante
enlace con yt-dlp (flujo secundario), validaciones de formato/tamaño/duración, listado de videos, estados
de procesamiento visibles, conservación del video original y eliminación con limpieza de registros y
archivos. Satisface RF-04, RF-05, RF-06, RF-14, RF-18 y los casos de uso CU-02 y CU-06.

## Requirements

### Requirement: Subir un video desde el equipo
El sistema SHALL aceptar archivos en formato mp4, mov, mkv, webm o avi de hasta 500 MB
(MoSCoW: Must — RF-04).

#### Scenario: Subida válida
- **WHEN** el usuario sube un archivo válido de hasta 500 MB en `/videos/new/`
- **THEN** el sistema crea un registro `Video` en estado `pending` con `source_type='upload'`, encola la tarea de procesamiento y redirige a la página de detalle con progreso

#### Scenario: Formato no permitido
- **WHEN** el archivo tiene una extensión distinta de mp4, mov, mkv, webm o avi
- **THEN** el formulario muestra el error en español y no se crea ningún registro

#### Scenario: Tamaño excedido
- **WHEN** el archivo supera 500 MB
- **THEN** el rechazo lo hace el Ingress con 413 y el usuario recibe un mensaje en español; si la petición llegara a la aplicación, el formulario también lo rechaza y no se crea ningún registro

#### Scenario: Archivo corrupto o sin flujo de video
- **WHEN** el worker no puede leer el archivo con ffprobe o no contiene una pista de video
- **THEN** el video queda en estado `failed` con un mensaje legible

### Requirement: Cargar un video mediante enlace
El sistema SHALL aceptar un enlace (YouTube u otros sitios de video) y SHALL descargar el video en segundo
plano con yt-dlp, como flujo secundario (MoSCoW: Should — RF-05).

#### Scenario: Enlace válido
- **WHEN** el usuario pega una URL `http` o `https` válida y envía el formulario
- **THEN** se crea un `Video` con `source_type='url'` y `source_url`, y la descarga ocurre en el worker (estado `downloading`)

#### Scenario: Enlace mal formado o con esquema no permitido
- **WHEN** el usuario envía un texto que no es una URL `http`/`https` válida
- **THEN** el formulario muestra el error en español y no se crea ningún registro

#### Scenario: Enlace a un recurso interno
- **WHEN** la URL apunta a una dirección privada, local o de la red del clúster
- **THEN** el sistema la rechaza sin descargar nada y muestra un mensaje en español

#### Scenario: Enlace no descargable
- **WHEN** la descarga con yt-dlp fracasa por bloqueo de la plataforma de origen
- **THEN** el video queda en estado `failed` con un mensaje legible que sugiere subir el archivo local

### Requirement: Rechazar videos largos
El sistema SHALL rechazar videos de más de 20 minutos (1200 s) (MoSCoW: Must — RF-06) y, cuando yt-dlp
exponga la duración antes de descargar, SHALL rechazar el enlace sin descargar el video.

#### Scenario: Duración excedida
- **WHEN** el worker valida la duración del video y supera los 1200 segundos
- **THEN** el video queda en estado `failed` con un mensaje claro al usuario

#### Scenario: Duración en el límite
- **WHEN** el video dura exactamente 1200 segundos
- **THEN** el video se acepta y continúa el procesamiento

#### Scenario: Enlace de video largo
- **WHEN** los metadatos del enlace indican una duración mayor a 1200 segundos
- **THEN** el video queda en `failed` con un mensaje claro y no se descarga el archivo

### Requirement: Conservar el video original
El sistema SHALL conservar el archivo del video original mientras exista el registro `Video`, porque el
re-recorte de clips (`recut_clip`) lo necesita, y SHALL eliminarlo solo junto con el video.

#### Scenario: Re-recorte posterior
- **WHEN** el pipeline termina (`done`) y más tarde el usuario ajusta un clip
- **THEN** el archivo original sigue disponible para regenerar el clip

### Requirement: Listar los videos del usuario
El sistema SHALL mostrar en `/dashboard/` los videos del usuario ordenados del más reciente al más
antiguo, con título, estado y progreso (CU-02).

#### Scenario: Dashboard con videos
- **WHEN** un usuario autenticado abre `/dashboard/`
- **THEN** ve solo sus propios videos, del más reciente al más antiguo, cada uno con su estado y progreso

#### Scenario: Dashboard vacío
- **WHEN** un usuario sin videos abre `/dashboard/`
- **THEN** ve un mensaje en español que lo invita a subir su primer video

### Requirement: Progreso visible del procesamiento
El sistema SHALL mostrar el estado y el porcentaje de progreso del procesamiento, actualizados cada 2 s
(MoSCoW: Must — RF-14).

#### Scenario: Sondeo de estado
- **WHEN** el navegador consulta `/videos/<id>/status/`
- **THEN** responde JSON `{status, progress, error, clips_count}` y la interfaz actualiza la barra de progreso

#### Scenario: Video fallido
- **WHEN** el video está en `failed`
- **THEN** la respuesta incluye el mensaje legible en `error` y la interfaz lo muestra al usuario

### Requirement: Estados del video
El sistema SHALL representar el ciclo de vida con los estados `pending` (0), `downloading` (10),
`transcribing` (40), `scoring` (70), `clipping` (90), `done` (100) y `failed`, siendo `failed` alcanzable
desde cualquier estado con mensaje legible en el campo `error`. El estado `downloading` aplica solo a
videos con `source_type='url'`.

#### Scenario: Recorrido exitoso
- **WHEN** el pipeline avanza por las fases del procesamiento
- **THEN** `status` y `progress` reflejan la fase correspondiente hasta `done` (100)

#### Scenario: Fallo en cualquier fase
- **WHEN** ocurre un error en cualquier fase
- **THEN** `status` pasa a `failed`, `error` contiene un mensaje legible y `progress` no llega a 100

### Requirement: Eliminar video con limpieza total
El sistema SHALL eliminar el video, su transcripción, sus clips y todos los archivos asociados (video
original, mp4 y miniaturas de clips, archivos temporales) (MoSCoW: Must — RF-18). El borrado en cascada de
la base de datos no elimina archivos, por lo que la limpieza de archivos SHALL hacerse explícitamente.

#### Scenario: Eliminación de un video
- **WHEN** el dueño envía `POST /videos/<id>/delete/`
- **THEN** se borran el registro `Video` (Cascade de `Transcript` y `Clip`) y todos los archivos del video en el almacén de medios, y se redirige al dashboard

#### Scenario: Eliminación durante el procesamiento
- **WHEN** el dueño elimina un video que aún se está procesando
- **THEN** la tarea en curso se cancela o aborta al detectar que el video ya no existe, y no quedan registros ni archivos huérfanos
