# Interfaz web

## Purpose

Experiencia de usuario del monolito Django con plantillas MVT, CSS propio (tema oscuro) y JavaScript sin
framework (ADR-09, respeta MVT y reduce complejidad frente a una SPA con React). Interfaz responsiva en
español, con flujo dashboard → subida → progreso → panel de clips y editor de tijera para el navegador
de escritorio y móvil, avisos al usuario y contrato de errores HTTP.
Satisface RF-01..03 (vistas), RF-14, RF-15, RNF-10 y los casos de uso CU-01..CU-06.

## Requirements

### Requirement: Interfaz responsiva en español
El sistema SHALL presentar una interfaz responsiva en español que funcione en escritorio y móvil (RNF-10).

#### Scenario: Vista en móvil
- **WHEN** un usuario abre el dashboard o el panel de clips desde un navegador móvil
- **THEN** la interfaz se adapta al ancho del dispositivo sin perder funcionalidad

### Requirement: Plantillas por app
El sistema SHALL renderizar la interfaz con plantillas de Django organizadas por app:
`accounts/*.html` (login, registro, logout), `videos/*.html` (subida, detalle, progreso),
`clips/*.html` (panel, editor) y `model/*.html` (página del modelo).

#### Scenario: Plantilla de cada app
- **WHEN** se renderiza una vista de `accounts`, `videos`, `clips` o `scoring`
- **THEN** usa una plantilla de la carpeta de su app

### Requirement: Flujo principal
El sistema SHALL guiar al usuario por el flujo dashboard → subida → progreso → panel de clips.

#### Scenario: Flujo principal
- **WHEN** un usuario autenticado entra al `/dashboard/`
- **THEN** ve sus videos, puede subir uno nuevo y seguir el progreso hasta el panel de clips

### Requirement: Avisos al usuario
El sistema SHALL mostrar un aviso de derechos sobre el contenido en el formulario de subida y SHALL
indicar en el panel de clips que el puntaje es una estimación de potencial viral.

#### Scenario: Aviso legal
- **WHEN** el usuario abre `/videos/new/`
- **THEN** ve un aviso de que debe tener derechos sobre el contenido que sube

#### Scenario: Aviso del puntaje
- **WHEN** el usuario abre el panel de clips
- **THEN** ve que el puntaje estima el potencial y no garantiza resultados en redes sociales

### Requirement: JavaScript sin framework
El sistema SHALL usar JavaScript plano sin framework para las interacciones dinámicas (sondeo de estado
cada 2 s y editor de tijera `editor.js`); la reproducción con Range la realiza el elemento `<video>` del navegador.

#### Scenario: Sondeo de estado
- **WHEN** el usuario está en la página de detalle de un video en proceso
- **THEN** el navegador consulta `/videos/<id>/status/` cada 2 s y deja de consultar al llegar a `done` o `failed`

#### Scenario: Error de red en el sondeo
- **WHEN** una consulta de estado falla por red
- **THEN** la interfaz reintenta en el siguiente ciclo sin mostrar un error definitivo

#### Scenario: Editor de tijera en el navegador
- **WHEN** el usuario abre el editor de un clip
- **THEN** `editor.js` posiciona las manijas de inicio/fin, valida en cliente y envía `POST /clips/<id>/trim/`

### Requirement: Tema visual oscuro propio
El sistema SHALL aplicar CSS propio con tema oscuro sin frameworks de UI externos.

#### Scenario: Estilo coherente
- **WHEN** el usuario navega por cualquier página
- **THEN** el tema oscuro visual y tipografía son coherentes en todas las vistas

### Requirement: Errores HTTP y mensajes en español
El sistema SHALL presentar los mensajes de error en español (RNF-10), con errores HTTP según el contrato:
400 (JSON `{error, code}`), 403, 404, 413 y 500 genérico sin exponer detalles internos. Los fallos del
procesamiento no son errores HTTP: se muestran mediante el campo `error` del `Video`.

#### Scenario: Entrada inválida
- **WHEN** una petición envía entrada inválida (formato, límites de recorte o texto vacío)
- **THEN** responde 400 con JSON `{error, code}` con mensaje en español

#### Scenario: Error interno
- **WHEN** ocurre un error no controlado en una vista
- **THEN** el usuario recibe un 500 genérico en español y el detalle queda en el log

#### Scenario: Fallo de CSRF
- **WHEN** un POST llega sin token CSRF válido
- **THEN** responde 403 con mensaje en español
