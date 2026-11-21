# Despliegue e infraestructura

## Purpose

Empaquetado y despliegue del sistema en Kubernetes con Kustomize (kind o minikube en local), con una única
imagen Docker para web y worker, recursos escalables y persistentes, sondas de salud, configuración por
variables de entorno y logs consultables. Satisface RNF-01, RNF-03, RNF-04..RNF-07, RNF-09 y RNF-12, y el
objetivo específico 5 (despliegue reproducible en Kubernetes).

## Requirements

### Requirement: Imagen Docker única
El sistema SHALL usar una única imagen Docker para `web` y `worker`, ejecutando de forma idéntica en
local y en el clúster (RNF-09).

#### Scenario: Portabilidad
- **WHEN** se despliega la misma imagen en local (compose o kind/minikube) o en el clúster
- **THEN** la configuración es idéntica y cambia solo por variables de entorno

### Requirement: Ingress con límite de subida
El sistema SHALL exponer la aplicación mediante Ingress NGINX con límite de cuerpo de 500 MB y tiempos de
espera suficientes para completar una subida de ese tamaño.

#### Scenario: Subida de 500 MB
- **WHEN** un usuario sube un archivo de 500 MB
- **THEN** el Ingress y gunicorn completan la subida sin cortarla por tiempo de espera

#### Scenario: Archivo mayor al límite
- **WHEN** el cuerpo de la petición supera 500 MB
- **THEN** el Ingress responde 413

### Requirement: Web escalable
El sistema SHALL desplegar `web` como Deployment con Service y HPA (gunicorn, 1–3 réplicas), con
solicitudes de recursos definidas para que el HPA pueda calcular la utilización.

#### Scenario: Aumento de carga
- **WHEN** la utilización supera el objetivo del HPA
- **THEN** el HPA incrementa las réplicas de `web` hasta un máximo de 3

### Requirement: Workers escalables
El sistema SHALL desplegar `worker` como Deployment de Celery que escala con `kubectl scale` (RNF-03).

#### Scenario: Escalado horizontal de workers
- **WHEN** el administrador ejecuta `kubectl scale` sobre el deployment `worker`
- **THEN** el procesamiento en paralelo aumenta con la nueva réplica

### Requirement: Base de datos y cola
El sistema SHALL desplegar MySQL como StatefulSet con PVC y Redis como Deployment, ambos accesibles solo
dentro del clúster.

#### Scenario: Servicios internos
- **WHEN** se revisan los Services de `mysql` y `redis`
- **THEN** son de tipo ClusterIP y no están expuestos por el Ingress

### Requirement: Medios compartidos entre web y worker
El sistema SHALL montar el PVC `media` en `web` y en `worker` de forma que ambos accedan al mismo contenido
simultáneamente, también cuando sus pods corran en nodos distintos.

#### Scenario: Archivo subido por la web
- **WHEN** la web guarda un video subido en `media`
- **THEN** cualquier réplica del worker puede leerlo y escribir sus clips en el mismo volumen

### Requirement: Migraciones antes del tráfico
El sistema SHALL ejecutar las migraciones con el Job `migrate` y SHALL NOT marcar como listos los pods de
`web` hasta que las migraciones estén aplicadas.

#### Scenario: Migraciones antes del tráfico
- **WHEN** se despliega una versión nueva con cambios de esquema
- **THEN** el Job `migrate` termina antes de que la web reciba tráfico

### Requirement: Datos persistentes
El sistema SHALL mantener los datos en volúmenes persistentes (MySQL en PVC; videos y clips en el PVC
`media`) para que sobrevivan a reinicios de pods (RNF-07).

#### Scenario: Reinicio de un pod
- **WHEN** un pod se reinicia
- **THEN** los datos de la base y los archivos de medios persisten gracias a los volúmenes

### Requirement: Sondas de salud
El sistema SHALL exponer `/healthz/` (liveness, sin consultar dependencias) y `/readyz/` (readiness, que
verifica la base de datos), sin requerir sesión y sin depender de la cabecera `Host`, respondiendo 200 o 503.

#### Scenario: Readiness con base de datos caída
- **WHEN** la base de datos no responde y Kubernetes consulta `/readyz/`
- **THEN** el endpoint responde 503 y el pod es marcado como no listo automáticamente

#### Scenario: Sonda del kubelet
- **WHEN** el kubelet consulta `/healthz/` usando la IP del pod como `Host`
- **THEN** responde 200 y no es rechazado por `ALLOWED_HOSTS`

### Requirement: Configuración por variables de entorno
El sistema SHALL recibir su configuración mediante ConfigMap y Secret de Kubernetes, y los artefactos v6
de `ml_artifacts/` SHALL estar disponibles para `web` y `worker`, incorporados en la imagen Docker única.

#### Scenario: Configuración del entorno
- **WHEN** se despliega en un entorno nuevo
- **THEN** solo cambian las variables del ConfigMap/Secret y `MOCK_SCORER` queda desactivado por defecto

### Requirement: Seguridad en el despliegue
El sistema SHALL configurar secretos solo por variables de entorno y Secrets de Kubernetes, sin
secretos en el repositorio, con protección CSRF, validación de entradas y límites de subida
(RNF-05, RNF-06) y ejecutando `subprocess` sin shell.

#### Scenario: Secretos fuera del repositorio
- **WHEN** se revisa el repositorio o se despliega
- **THEN** las credenciales provienen de ConfigMap/Secret de Kubernetes y las variables de entorno

### Requirement: Logs en salida estándar
El sistema SHALL escribir los logs de `web` y `worker` en la salida estándar para consultarlos con
`kubectl logs` (RNF-12).

#### Scenario: Consulta de un fallo
- **WHEN** el administrador ejecuta `kubectl logs` sobre el worker tras un fallo de pipeline
- **THEN** encuentra la traza técnica completa del error
