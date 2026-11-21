# Manual de usuario y despliegue

## Usuario

1. Crear cuenta o iniciar sesión.
2. Subir un video.
3. Esperar a que el estado cambie a completado.
4. Revisar los clips por puntaje.
5. Ajustar la tijera y descargar.

## Desarrollo local

```bash
docker compose up --build
docker compose exec web python manage.py migrate
```

## Kubernetes

```bash
kubectl apply -k k8s/base
```

Consultar `README.md` y la guía de verificación de esta carpeta para variables y comprobaciones.
