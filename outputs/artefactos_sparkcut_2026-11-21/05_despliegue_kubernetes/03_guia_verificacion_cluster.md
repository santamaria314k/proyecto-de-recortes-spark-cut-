# Guía de verificación del clúster

```bash
kubectl apply -k k8s_base/
kubectl get pods -w
kubectl logs deploy/sparkcut-web
kubectl logs deploy/sparkcut-worker
kubectl get ingress,pvc,job
```

La evidencia de “sistema en el clúster” debe incluir la salida de esos comandos y capturas con fecha. Esta carpeta contiene los manifiestos; la ejecución depende del clúster local o remoto del equipo.
