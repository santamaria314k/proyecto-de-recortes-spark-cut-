# Refinamiento de los specs de SparkCut

Archivos modificados: los 7 `spec.md`, `config.yaml` y `project.md` (cambios puntuales).

## 1. Correcciones (errores o inconsistencias)

- **pipeline**: se eliminó la palabra «waste» en «Video sin voz»; se corrigió «la transcripción detectado idioma español»; se quitó «modelo ligero» (contradecía el ensamble de 3 BiGRU).
- **modelo-ia**: «SHALL NO iniciar» pasa a «SHALL NOT»; el escenario «Fragmento viral» se renombró a «Puntaje de una ventana»; los pesos 0.6/0.2/0.2 estaban fijos en el spec pero `project.md` dice que viven en `config.json`: ahora el spec y `project.md` coinciden (se leen de `config.json`).
- **modelo-ia**: la carga de artefactos decía «la aplicación», pero `/modelo/probar/` corre en la web; ahora se distingue worker (falla al iniciar) y web (lee los mismos artefactos).
- **clips / project.md**: `/clips/<id>/media/` responde 206 solo con `Range`; sin cabecera, 200; rango inválido, 416.
- **clips**: se sacó el detalle de índice `(video_id, score)` de un escenario (es implementación).
- **despliegue**: el requirement «Sondeo de errores y mensajes en español» estaba mal ubicado y mal titulado; se movió a `interfaz-web` como «Errores HTTP y mensajes en español». «Observabilidad de fallos» pasó a `pipeline` (trazas) y a despliegue solo queda «Logs en salida estándar».
- **despliegue**: el escenario de portabilidad decía «compose» mientras el Purpose decía kind/minikube; ahora menciona ambos.
- **interfaz-web**: el sondeo y el `<video>` con Range se atribuían a JS; la reproducción con Range la hace el navegador.
- **project.md**: erratas «limites» y «sessiones».

## 2. Aclaraciones

- Solapamiento (`max_overlap`): se midió sobre el intervalo **más corto** y la selección es voraz por puntaje descendente.
- Umbral: 70.0 exacto no es `high` (escenario de borde).
- El respaldo `medium` también respeta el solapamiento máximo y maneja menos de 3 candidatos.
- El estado `downloading` solo aplica a `source_type='url'`.
- Recorte: `start`/`end` están en la línea de tiempo del video original y el puntaje/explicación no se recalculan al editar.
- Corte con precisión de fotograma implica recodificar.
- Golden tests con tolerancia (indicada en `golden_tests.json`).
- Correlación puntaje-posición: se añadió un escenario de determinismo, que sí es verificable.

## 3. Adiciones propuestas (revisar y aprobar)

Ninguna tiene RF/RNF asignado; conviene asignarlo.

| Spec | Adición |
|---|---|
| autenticacion | Acceso restringido (redirige en HTML, 403 en JSON); admin de Django (CU-08, no estaba en ningún spec); enlace de Google solo con correo verificado; correo duplicado, contraseña débil, autorización denegada |
| gestion-de-videos | Conservar el video original (lo necesita `recut_clip`); listado del dashboard con estado vacío; URL mal formada o interna (riesgo SSRF con yt-dlp); rechazo previo por duración en enlaces; borrado durante el procesamiento; limpieza explícita de archivos (el CASCADE no borra archivos) |
| pipeline | Extracción de audio sin pista; sin ventanas válidas → `failed`; fallo de ffmpeg → `failed` sin clips parciales; límite de tiempo de la tarea; limpieza de temporales |
| clips | Reproducción con Range separada; 409 si hay re-recorte en curso; recorte fuera de los límites del video (400); fallo de `recut_clip`; restaurar sobre clip sin editar; estado del re-recorte; clip sin `explanation`; panel con video `failed` y clips `medium` |
| modelo-ia | Versión y limitaciones en `/modelo/`; 400 en el probador; coherencia entre `model_*.pt` y `config.json`; `MOCK_SCORER` desactivado por defecto |
| despliegue | Timeouts de subida de 500 MB; PVC `media` accesible desde varios pods; sondas independientes de `Host`; `ml_artifacts` disponible en web y worker; logs a stdout |
| interfaz-web | Aviso legal en la subida y aviso del puntaje (estaban solo en `project.md`); el sondeo se detiene en `done`/`failed` |

## 4. Decisiones pendientes (no las resolví)

1. **Estado del re-recorte**: el modelo `Clip` no tiene campo de estado, pero `/clips/<id>/status/` y el 409 lo necesitan. ¿Se agrega `Clip.status` o se usa el resultado de Celery?
2. **Código 409** y **403 en JSON no autenticado**: no están en el contrato de errores de `project.md`; hay que acordarlos.
3. **Endpoint de exportación 9:16**: no existe en la tabla de endpoints (RF-20, Could).
4. **Traducción al inglés**: resuelto con la pasada `task="translate"` de Whisper (sin dependencias ni servicios extra), emparejada por tiempo con los segmentos. `Clip.text` guarda el original y las ventanas puntúan `text_en`; `/modelo/probar/` no traduce texto escrito porque solo hay audio en la transcripción.
5. **Migraciones antes del tráfico**: Kustomize no ordena Jobs; falta el mecanismo (initContainer que espere `migrate` o que `/readyz/` verifique migraciones pendientes).
6. **PVC `media` compartido**: requiere ReadWriteMany (o afinidad de nodo) si hay varias réplicas de web; en kind/minikube de un nodo no se nota.
7. **Redis sin persistencia**: un reinicio pierde tareas encoladas y deja videos en `pending`/intermedios. ¿Se agrega recuperación (p. ej. `acks_late` o un barrido de videos estancados)?
8. **Retención**: el video original se conserva hasta que el usuario lo borre; ¿hace falta una política de expiración por espacio?
9. **Umbral de independencia de posición** y **tolerancia de golden tests**: hay que fijar valores.
10. **Sin voz suficiente**: lo dejé como `failed` con mensaje; la alternativa es `done` con 0 clips.
11. **Probador público** (`/modelo/probar/`): sin sesión y sin límite de tasa; ¿se limita?
