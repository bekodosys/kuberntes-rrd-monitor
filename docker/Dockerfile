FROM python:3.11-slim

# 1. Instalar dependencias del sistema
# AÑADIDO: 'bc' para los cálculos en bash y 'jq' para procesar el JSON
RUN apt-get update && apt-get install -y \
    rrdtool \
    cron \
    jq \
    bc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Instalar dependencias Python
# Recuerda lanzar el build desde la raíz del proyecto para que encuentre docker/requirements.txt
COPY docker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copiar scripts
COPY get_metrics_cluster.py .
COPY rrd_grapher.sh .
RUN chmod +x rrd_grapher.sh

# 4. Configurar Cron (TU CAMBIO APLICADO)
# Usamos 'cd /app &&' para asegurar el path correcto de ejecución
RUN echo "*/5 * * * * root cd /app && ./rrd_grapher.sh >> /proc/1/fd/1 2>> /proc/1/fd/2" >> /etc/crontab
# Truco de veterano: Cron a veces ignora la última línea si no tiene salto de línea
RUN echo "\n" >> /etc/crontab

# 5. Arrancar Cron en primer plano
CMD ["cron", "-f"]