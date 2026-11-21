# Clips

## Purpose

Panel de clips con previsualización y puntaje, editor de recorte (tijera) para ajustar inicio y fin,
restaurar el recorte automático original, exportación vertical 9:16 con subtítulos (opcional), y
descarga/eliminación con soporte de Range para reproducción. Satisface RF-15..RF-20 y los casos de uso
CU-04, CU-05 y CU-06.

## Requirements

### Requirement: Panel principal de clips
El sistema SHALL listar los clips ordenados por puntaje de mayor a menor con tarjetas que permiten
reproducir la previsualización y muestran puntaje y emociones principales, diferenciando visualmente los
clips de potencial medio (MoSCoW: Must — RF-15).

#### Scenario: Revisión de clips
- **WHEN** el dueño abre `/videos/<id>/clips/` de un video en estado `done`
- **THEN** los clips se listan ordenados por puntaje y se reproducen con `/clips/<id>/media/`

#### Scenario: Clips de potencial medio
- **WHEN** el video tiene clips con `tier='medium'`
- **THEN** las tarjetas se muestran diferenciadas como «potencial medio»

#### Scenario: Video todavía en proceso
- **WHEN** el video aún no está en `done`
- **THEN** la interfaz muestra la barra de progreso del procesamiento

#### Scenario: Video fallido
- **WHEN** el video está en `failed`
- **THEN** la interfaz muestra el mensaje de error legible en lugar del panel de clips

### Requirement: Reproducción con soporte de Range
El sistema SHALL servir el mp4 del clip en `/clips/<id>/media/` con soporte de peticiones Range para
permitir reproducir y avanzar en el navegador.

#### Scenario: Petición con Range
- **WHEN** el navegador solicita `/clips/<id>/media/` con una cabecera `Range` válida
- **THEN** el servidor responde 206 Partial Content con `Content-Range` y solo los bytes pedidos

#### Scenario: Petición sin Range
- **WHEN** se solicita `/clips/<id>/media/` sin cabecera `Range`
- **THEN** el servidor responde 200 con el archivo completo

#### Scenario: Range inválido
- **WHEN** la cabecera `Range` queda fuera del tamaño del archivo
- **THEN** el servidor responde 416

### Requirement: Editor de recorte (tijera)
El sistema SHALL permitir ajustar inicio y fin de un clip, expresados en segundos sobre la línea de tiempo
del video original: el usuario guarda nuevos límites y el servidor regenera el clip (MoSCoW: Must — RF-16).
El puntaje y la explicación del clip no se recalculan al editarlo.

#### Scenario: Recorte válido
- **WHEN** el dueño envía `POST /clips/<id>/trim/` con `{start, end}` tales que `start < end`, `0 ≤ start`, `end ≤ duration_s` del video y la duración queda entre 3 y 90 s
- **THEN** la respuesta es 202, se encola la tarea `recut_clip`, el clip queda `edited=true` y el panel actualiza la previsualización al terminar

#### Scenario: Límites inválidos
- **WHEN** `start >= end`, la duración queda fuera de 3 a 90 segundos o los límites quedan fuera del video
- **THEN** la respuesta es 400 con JSON `{error, code}` en español y el clip no cambia

#### Scenario: Re-recorte en curso
- **WHEN** el dueño envía `POST /clips/<id>/trim/` mientras el clip aún se está regenerando
- **THEN** la respuesta es 409 con mensaje en español y no se encola otra tarea

#### Scenario: Fallo del re-recorte
- **WHEN** la tarea `recut_clip` falla
- **THEN** el clip conserva el mp4 y los límites anteriores, su estado indica `failed` y el panel muestra un mensaje en español

### Requirement: Estado del re-recorte
El sistema SHALL informar el estado del re-recorte de un clip en `GET /clips/<id>/status/` mediante JSON
`{status}` con los valores `processing`, `ready` o `failed`.

#### Scenario: Sondeo del re-recorte
- **WHEN** el navegador consulta `/clips/<id>/status/` durante un re-recorte
- **THEN** responde `{"status": "processing"}` y, al terminar, `{"status": "ready"}`

### Requirement: Restaurar el recorte automático original
El sistema SHALL permitir devolver el clip a sus límites originales propuestos por la IA
(`orig_start_time`, `orig_end_time`) (MoSCoW: Should — RF-17).

#### Scenario: Restaurar IA
- **WHEN** el dueño envía `POST /clips/<id>/restore/` sobre un clip editado
- **THEN** los límites vuelven a los originales, `edited` pasa a `false`, se encola `recut_clip` y la respuesta es JSON

#### Scenario: Clip sin editar
- **WHEN** el dueño envía `POST /clips/<id>/restore/` sobre un clip con `edited=false`
- **THEN** el sistema no regenera el clip y responde JSON indicando que ya tiene el recorte original

### Requirement: Descargar y eliminar clips
El sistema SHALL descargar el mp4 del clip y eliminar clips con sus registros y archivos
(MoSCoW: Must — RF-18).

#### Scenario: Descarga
- **WHEN** el dueño solicita `GET /clips/<id>/download/`
- **THEN** el servidor entrega el archivo mp4 como adjunto

#### Scenario: Eliminación
- **WHEN** el dueño envía `POST /clips/<id>/delete/`
- **THEN** se borran el registro `Clip` y sus archivos (mp4 y miniatura) y se redirige al panel

#### Scenario: Eliminación durante un re-recorte
- **WHEN** el dueño elimina un clip que se está regenerando
- **THEN** el clip se elimina y la tarea `recut_clip` no deja archivos huérfanos

### Requirement: Explicación del puntaje
El sistema SHALL listar en la tarjeta del clip las 3 emociones principales usando el campo
`explanation` JSON (emociones dominantes y dimensiones del puntaje) (MoSCoW: Should — RF-19).

#### Scenario: Emociones dominantes
- **WHEN** la puntuación devuelve detalles con `top_emotions`
- **THEN** la tarjeta muestra las 3 emociones principales del fragmento

#### Scenario: Clip sin explicación
- **WHEN** el clip no tiene `explanation` (por ejemplo, con `MOCK_SCORER=1`)
- **THEN** la tarjeta muestra el puntaje sin la lista de emociones y sin error

### Requirement: Exportación vertical 9:16 (opcional)
El sistema SHALL soportar la exportación del clip en formato vertical 9:16 con subtítulos, cuando se
solicite (MoSCoW: Could — RF-20). El endpoint de exportación SHALL definirse en el contrato de
`project.md` antes de implementarse.

#### Scenario: Exportación 9:16
- **WHEN** el usuario solicita la exportación vertical de un clip
- **THEN** se descarga un mp4 de 1080x1920 con subtítulos
