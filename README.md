# Kubernetes RRD Monitor

Monitor de métricas ligero para clusters Kubernetes que genera gráficas RRD (Round Robin Database) históricas de CPU y Memoria (Día, Semana, Mes, Año).

## Arquitectura
- **Worker (StatefulSet):** Python script que consulta la API de Kubernetes cada 5 minutos (Cron) y actualiza las BBDD RRD.
- **Frontend (Nginx):** Sirve los ficheros estáticos HTML y las imágenes PNG generadas. Protegido con Basic Auth.
- **Persistencia:** PVC `rrd-data-pvc` compartido entre worker y nginx.

## 1. Prerrequisitos
- Cluster Kubernetes.
- `kubectl` configurado.
- Docker para construir la imagen.

## 2. Construcción de la Imagen
Si realizas cambios en el código (`get_metrics_cluster.py`, `rrd_grapher.sh` o `index.html`), debes reconstruir la imagen.

```bash
# Define tu registry
export REGISTRY="bekodo"

# Construir y subir (desde la raíz del proyecto)
docker build --platform linux/amd64 -t $REGISTRY/kubernetes-rrd-monitor:latest -f docker/Dockerfile .
docker push $REGISTRY/kubernetes-rrd-monitor:latest
```

## 3. Generar Credenciales (Basic Auth)
El acceso web está protegido. Debes generar un secreto con el usuario y contraseña deseados.

1. **Generar hash de contraseña (htpasswd)**:
   Si tienes `htpasswd` instalado (apache2-utils):
   ```bash
   htpasswd -n -b -B miusuario mipassword
   # Salida ejemplo: miusuario:$2y$05$G...
   ```
   
   O usando Docker si no quieres instalar nada:
   ```bash
   docker run --rm -it httpd:alpine htpasswd -n -b -B miusuario mipassword
   ```

2. **Codificar en Base64**:
   Copia la cadena de salida del paso anterior y codifícala en base64:
   ```bash
   echo -n 'miusuario:$2y$05$G...' | base64
   ```

3. **Actualizar el Secreto**:
   Edita el archivo `kubectl/07-secret.yaml` y pega el resultado en la clave `.htpasswd`:
   ```yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: rrd-basic-auth
     namespace: rrd-monitor
   type: Opaque
   data:
     .htpasswd: <TU_CADENA_BASE64_AQUI>
   ```

## 4. Despliegue en Kubernetes

El orden de aplicación es importante:

### 1. Infraestructura y Configuración
```bash
# Crear Namespace y ConfigMap (Dashboard HTML)
kubectl apply -f kubectl/06-configmap.yaml

# Cuentas de Servicio y Roles (RBAC)
kubectl apply -f kubectl/00-serviceaccount.yaml
kubectl apply -f kubectl/01-clusterrole.yaml
kubectl apply -f kubectl/02-clusterRoleBinding.yaml

# Secretos y Configuración Nginx
kubectl apply -f kubectl/07-secret.yaml
kubectl apply -f kubectl/08-nginx-config.yaml
```

### 2. Aplicación
```bash
# Servicio Interno
kubectl apply -f kubectl/05-service.yaml

# StatefulSet (La aplicación en sí)
kubectl apply -f kubectl/04-StatefulSet.yaml
```

### 3. Acceso Externo (Ingress)
Integrado bajo `tudominio.com/rrd`.
```bash
kubectl apply -f kubectl/03-ingress.yaml
```

## 5. Verificación y Logs

Verificar que los pods están corriendo:
```bash
kubectl get pods -n rrd-monitor -w
```

Ver logs del generador de gráficas:
```bash
kubectl logs -n rrd-monitor rrd-sts-0 -c worker
```

Acceso local rápido (Port Forward):
```bash
kubectl port-forward -n rrd-monitor sts/rrd-sts 8080:80
# Abrir en navegador: http://localhost:8080
```