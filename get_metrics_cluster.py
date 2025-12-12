import json
import sys
from kubernetes import client, config

def parse_cpu(quantity):
    """Convierte cadenas como '100m' o '0.5' a valor numérico (cores)."""
    if not quantity:
        return 0.0
    quantity = str(quantity)
    if quantity.endswith("n"):
        return float(quantity[:-1]) / 1_000_000_000
    if quantity.endswith("u"):
        return float(quantity[:-1]) / 1_000_000
    if quantity.endswith("m"):
        return float(quantity[:-1]) / 1000
    return float(quantity)

def parse_memory(quantity):
    """Convierte cadenas como '1024Ki' o '50Mi' a MiB (float)."""
    if not quantity:
        return 0.0
    quantity = str(quantity)
    units = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4}
    
    for unit, multiplier in units.items():
        if quantity.endswith(unit):
            bytes_val = float(quantity[:-len(unit)]) * multiplier
            return bytes_val / (1024**2) 
            
    return float(quantity) / (1024**2)

def get_pod_metrics_map(custom_api):
    """Obtiene métricas de pods. Si falla (ej. sin metrics-server), retorna vacío."""
    metrics_map = {}
    try:
        metrics = custom_api.list_cluster_custom_object(
            "metrics.k8s.io", "v1beta1", "pods"
        )
        for item in metrics['items']:
            pod_name = item['metadata']['name']
            namespace = item['metadata']['namespace']
            
            cpu_total = 0
            mem_total = 0
            
            for container in item['containers']:
                cpu_total += parse_cpu(container['usage']['cpu'])
                mem_total += parse_memory(container['usage']['memory'])
                
            metrics_map[(namespace, pod_name)] = {
                "cpu": cpu_total,
                "mem": mem_total
            }
    except Exception as e:
        # Escribir a stderr para no romper el formato JSON de salida
        sys.stderr.write(f"Warning: No se pudieron obtener metricas: {e}\n")
        pass
        
    return metrics_map

def main():
    # ---------------------------------------------------------
    # 1. AUTENTICACIÓN HÍBRIDA (Cluster vs Local)
    # ---------------------------------------------------------
    try:
        # Intenta usar el ServiceAccount token inyectado en /var/run/secrets
        config.load_incluster_config()
        sys.stderr.write("Info: Usando In-Cluster Config (ServiceAccount)\n")
    except config.ConfigException:
        # Fallback a local ~/.kube/config para cuando pruebas en tu máquina
        config.load_kube_config()
        sys.stderr.write("Info: Usando Local Kube Config\n")
    
    # 2. Inicializar clientes de API
    app_api = client.AppsV1Api()           # Deployments
    core_api = client.CoreV1Api()          # Pods
    custom_api = client.CustomObjectsApi() # Metrics
    
    # 3. Obtener datos crudos
    try:
        deployments = app_api.list_deployment_for_all_namespaces().items
        pods = core_api.list_pod_for_all_namespaces().items
    except Exception as e:
        sys.stderr.write(f"Error critico obteniendo recursos K8s: {e}\n")
        sys.exit(1)

    metrics_map = get_pod_metrics_map(custom_api)
    
    datos_salida = []

    # 4. Procesar cada Deployment
    for dep in deployments:
        ns = dep.metadata.namespace
        name = dep.metadata.name
        replicas = dep.spec.replicas or 0
        
        sys_names = ["coredns", "local-path-provisioner", "metrics-server", "traefik"]
        if name in sys_names or ns == "kube-system":
            category = "SYS"
        else:
            category = "APP"

        cpu_usage = 0.0
        mem_usage = 0.0
        
        match_labels = dep.spec.selector.match_labels
        if match_labels:
            # Filtrado manual de pods asociados
            related_pods = [
                p for p in pods 
                if p.metadata.namespace == ns and 
                p.metadata.labels and # Check de seguridad por si labels es None
                all(p.metadata.labels.get(k) == v for k, v in match_labels.items())
            ]
            
            for pod in related_pods:
                pod_key = (pod.metadata.namespace, pod.metadata.name)
                if pod_key in metrics_map:
                    cpu_usage += metrics_map[pod_key]["cpu"]
                    mem_usage += metrics_map[pod_key]["mem"]

        fila = {
            "category": category,
            "type": "Deployment",
            "name": name,
            "replicas": replicas,
            "cpu_v": round(cpu_usage, 3),
            "mem_mib": round(mem_usage, 1)
        }
        
        datos_salida.append(fila)

    # 6. Imprimir JSON limpio a STDOUT
    print(json.dumps(datos_salida, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()