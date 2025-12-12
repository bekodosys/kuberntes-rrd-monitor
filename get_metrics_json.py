import json
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
    # Diccionario de multiplicadores para convertir a Bytes
    units = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4}
    
    # Buscar unidad
    for unit, multiplier in units.items():
        if quantity.endswith(unit):
            bytes_val = float(quantity[:-len(unit)]) * multiplier
            return bytes_val / (1024**2) # Devolver en MiB
            
    # Si es solo numero, se asume bytes
    return float(quantity) / (1024**2)

def get_pod_metrics_map(custom_api):
    """Obtiene todas las métricas de pods y crea un diccionario para búsqueda rápida."""
    metrics_map = {}
    try:
        # Pide las métricas a la API metrics.k8s.io
        metrics = custom_api.list_cluster_custom_object(
            "metrics.k8s.io", "v1beta1", "pods"
        )
        for item in metrics['items']:
            pod_name = item['metadata']['name']
            namespace = item['metadata']['namespace']
            
            cpu_total = 0
            mem_total = 0
            
            # Sumar consumo de todos los contenedores dentro del pod
            for container in item['containers']:
                cpu_total += parse_cpu(container['usage']['cpu'])
                mem_total += parse_memory(container['usage']['memory'])
                
            metrics_map[(namespace, pod_name)] = {
                "cpu": cpu_total,
                "mem": mem_total
            }
    except Exception as e:
        # Si falla (ej. no hay metrics-server), devolvemos mapa vacío pero no rompemos el script
        pass
        
    return metrics_map

def main():
    # 1. Cargar configuración de Kubernetes (busca ~/.kube/config)
    config.load_kube_config(context="triviere-pro")
    
    # 2. Inicializar clientes de API
    app_api = client.AppsV1Api()       # Para Deployments
    core_api = client.CoreV1Api()      # Para Pods
    custom_api = client.CustomObjectsApi() # Para Metrics
    
    # 3. Obtener datos crudos
    deployments = app_api.list_deployment_for_all_namespaces().items
    pods = core_api.list_pod_for_all_namespaces().items
    metrics_map = get_pod_metrics_map(custom_api)
    
    # Lista final para el JSON
    datos_salida = []

    # 4. Procesar cada Deployment
    for dep in deployments:
        ns = dep.metadata.namespace
        name = dep.metadata.name
        replicas = dep.spec.replicas or 0
        
        # Filtrar lógica de sistema vs app (Personaliza esto a tu gusto)
        sys_names = ["coredns", "local-path-provisioner", "metrics-server", "traefik"]
        if name in sys_names or ns == "kube-system":
            category = "SYS"
            cat_icon = "⚙️"
        else:
            category = "APP"
            cat_icon = "❤️"

        # Calcular uso real sumando los pods asociados a este deployment
        cpu_usage = 0.0
        mem_usage = 0.0
        
        # Buscamos pods que pertenezcan a este deployment (usando match_labels)
        match_labels = dep.spec.selector.match_labels
        if match_labels:
            # Filtramos pods que coincidan con las etiquetas y el namespace
            related_pods = [
                p for p in pods 
                if p.metadata.namespace == ns and 
                all(p.metadata.labels.get(k) == v for k, v in match_labels.items())
            ]
            
            for pod in related_pods:
                pod_key = (pod.metadata.namespace, pod.metadata.name)
                if pod_key in metrics_map:
                    cpu_usage += metrics_map[pod_key]["cpu"]
                    mem_usage += metrics_map[pod_key]["mem"]

        # 5. Construir el objeto limpio
        fila = {
            "category": category,
            "type": "Deployment",
            "name": name,
            "replicas": replicas,
            "cpu_v": round(cpu_usage, 3),   # Redondear a 3 decimales
            "mem_mib": round(mem_usage, 1)  # Redondear a 1 decimal
        }
        
        datos_salida.append(fila)

    # 6. Imprimir SOLAMENTE el JSON
    print(json.dumps(datos_salida, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()