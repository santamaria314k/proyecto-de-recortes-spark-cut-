# Autenticación

## Purpose

Gestión de acceso de los creadores de contenido: registro e inicio de sesión con correo y contraseña,
inicio de sesión con cuenta de Google (OAuth 2.0) mediante django-allauth, cierre de sesión, control de
acceso a las rutas protegidas, aislamiento de datos por usuario y administración de usuarios desde el
admin de Django.
Satisface RF-01, RF-02, RF-03, RNF-04 y los casos de uso CU-01 y CU-08 del sistema SparkCut.

## Requirements

### Requirement: Registro e inicio de sesión con correo y contraseña
El sistema SHALL permitir registrar una cuenta nueva e iniciar sesión con correo y contraseña
(MoSCoW: Must — RF-01).

#### Scenario: Registro e ingreso exitoso
- **WHEN** un visitante se registra con un correo y contraseña válidos
- **THEN** su cuenta se crea, inicia sesión y accede a `/dashboard/`

#### Scenario: Credenciales inválidas
- **WHEN** el usuario envía credenciales inválidas en el formulario de acceso
- **THEN** el sistema muestra un mensaje de error (en español) y se mantiene en el formulario

#### Scenario: Correo ya registrado
- **WHEN** un visitante intenta registrarse con un correo que ya tiene cuenta
- **THEN** el sistema rechaza el registro, muestra un mensaje en español y no crea una cuenta duplicada

#### Scenario: Contraseña no válida
- **WHEN** el visitante envía una contraseña que no cumple los validadores de contraseña de Django
- **THEN** el sistema rechaza el registro y muestra los motivos en español

### Requirement: Inicio de sesión con Google (OAuth 2.0)
El sistema SHALL iniciar sesión mediante cuenta de Google creando o enlazando la cuenta por correo,
y SHALL enlazar con una cuenta existente solo cuando Google reporta el correo como verificado
(MoSCoW: Must — RF-02, django-allauth).

#### Scenario: Usuario nuevo con Google
- **WHEN** un visitante pulsa «Continuar con Google» y autoriza el acceso
- **THEN** el sistema crea la cuenta (o la enlaza por correo si ya existe), crea la sesión y redirige a `/dashboard/`

#### Scenario: Correo de Google sin verificar
- **WHEN** Google devuelve un correo que coincide con una cuenta existente pero no está verificado
- **THEN** el sistema no enlaza ni inicia sesión en la cuenta existente

#### Scenario: Autorización denegada
- **WHEN** el visitante cancela o deniega la autorización en Google
- **THEN** el sistema vuelve a la página de acceso con un mensaje en español y sin crear sesión

#### Scenario: Google sin configurar
- **WHEN** la autenticación con Google no está configurada en el entorno
- **THEN** el botón de Google no se muestra en la página de acceso

### Requirement: Cerrar sesión
El sistema SHALL permitir terminar la sesión activa mediante una petición POST protegida por CSRF
(MoSCoW: Must — RF-03).

#### Scenario: Cierre de sesión
- **WHEN** un usuario autenticado cierra sesión
- **THEN** la sesión termina y se redirige a la página de inicio

### Requirement: Acceso restringido a usuarios autenticados
El sistema SHALL exigir sesión iniciada en todas las rutas salvo `/`, `/accounts/*`, `/modelo/`,
`/modelo/probar/`, `/healthz/` y `/readyz/`.

#### Scenario: Visitante en una página protegida
- **WHEN** un visitante sin sesión solicita una ruta HTML protegida, por ejemplo `/dashboard/`
- **THEN** el sistema lo redirige al formulario de acceso y, tras autenticarse, lo devuelve a la ruta solicitada

#### Scenario: Visitante en un endpoint JSON protegido
- **WHEN** un visitante sin sesión solicita un endpoint JSON protegido, por ejemplo `/videos/<id>/status/`
- **THEN** el sistema responde 403 y no revela información del recurso

### Requirement: Aislamiento de datos por usuario
El sistema SHALL aislar los recursos por usuario: toda consulta filtra por `user_id` (RNF-04).

#### Scenario: Acceso a recurso ajeno
- **WHEN** un usuario autenticado solicita un recurso inexistente o de otro usuario
- **THEN** el sistema responde 404 y no revela información del recurso

#### Scenario: Acción de escritura sobre recurso ajeno
- **WHEN** un usuario autenticado envía una petición POST (eliminar, recortar o restaurar) sobre un recurso de otro usuario
- **THEN** el sistema responde 404 y no modifica ningún dato ni archivo

### Requirement: Administración de usuarios
El sistema SHALL permitir a los administradores gestionar usuarios desde el admin de Django, accesible
solo a cuentas con permiso de staff (CU-08).

#### Scenario: Administrador autorizado
- **WHEN** una cuenta de staff abre el admin de Django
- **THEN** puede listar, consultar y desactivar usuarios

#### Scenario: Usuario sin permiso de staff
- **WHEN** una cuenta sin permiso de staff intenta abrir el admin de Django
- **THEN** el sistema niega el acceso y no muestra datos de otros usuarios
