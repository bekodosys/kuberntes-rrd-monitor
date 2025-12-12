#!/bin/bash

# --- CONFIGURACIÓN ---
DIR_RRD="/data"
SCRIPT_PYTHON="./get_metrics_cluster.py"
CMD_PYTHON="python3.11"

# Dimensiones y colores
ANCHO=700
ALTO=250

# ¡AJUSTA ESTO A TU HARDWARE!
TOTAL_CPU_CORES=4.0
TOTAL_MEM_MIB=8192.0

# --- PALETA DE COLORES FIJA (10 COLORES) ---
# Diseñada para alto contraste sobre fondo oscuro
COLORES=(
    "#FF3333" # 1. Rojo brillante
    "#33FF33" # 2. Verde lima
    "#3380FF" # 3. Azul cielo
    "#FFFF33" # 4. Amarillo
    "#FF9933" # 5. Naranja
    "#33FFFF" # 6. Cian
    "#FF33FF" # 7. Magenta
    "#B366FF" # 8. Púrpura suave
    "#00CC99" # 9. Verde azulado (Teal)
    "#FF99CC" # 10. Rosa
)

mkdir -p "$DIR_RRD"

# 1. OBTENER DATOS
JSON_DATA=$($CMD_PYTHON $SCRIPT_PYTHON)

if [ -z "$JSON_DATA" ]; then
    echo "Error: No data from Python."
    exit 1
fi

# 2. ACTUALIZAR RRDs
echo "$JSON_DATA" | jq -r '.[] | "\(.name) \(.cpu_v) \(.mem_mib) \(.requests)"' | while read -r name cpu mem requests; do
    RRD_FILE="$DIR_RRD/$name.rrd"
    
    # CASO ESPECIAL: Traefik Global Requests
    if [ "$name" == "traefik-global-requests" ]; then
        if [ ! -f "$RRD_FILE" ]; then
            rrdtool create "$RRD_FILE" --step 300 \
                DS:requests:DERIVE:600:0:U \
                RRA:AVERAGE:0.5:1:288 \
                RRA:AVERAGE:0.5:6:336 \
                RRA:AVERAGE:0.5:24:372 \
                RRA:AVERAGE:0.5:288:366
        fi
        # DERIVE necesita valores enteros crecientes (contadores)
        rrdtool update "$RRD_FILE" N:$requests
        continue
    fi

    # CASO NORMAL: CPU/MEM Deployments
    if [ ! -f "$RRD_FILE" ]; then
        rrdtool create "$RRD_FILE" --step 300 \
            DS:cpu:GAUGE:600:0:U \
            DS:mem:GAUGE:600:0:U \
            RRA:AVERAGE:0.5:1:288 \
            RRA:AVERAGE:0.5:6:336 \
            RRA:AVERAGE:0.5:24:372 \
            RRA:AVERAGE:0.5:288:366
    fi
    rrdtool update "$RRD_FILE" N:$cpu:$mem
done

# 3. GENERAR GRÁFICA
generar_grafica() {
    TIPO=$1    # "cpu" o "mem"
    TOTAL=$2   # Capacidad total
    PERIODO=$3 # "day", "week", "month", "year"
    
    TITULO="Triviere Cluster - Uso $TIPO (%) - $PERIODO"
    OUT_IMG="$DIR_RRD/graph_${TIPO}_${PERIODO}.png"
    
    OPTS=(
        "graph" "$OUT_IMG"
        "--start" "-1$PERIODO"
        "-w" "$ANCHO" "-h" "$ALTO"
        "-a" "PNG"
        "--slope-mode"
        "--title" "$TITULO"
        "--vertical-label" "% Uso"
        "--lower-limit" "0"
        "--color" "CANVAS#000000"
        "--color" "FONT#FFFFFF"
        "--color" "BACK#000000"
        "--font" "DEFAULT:10:Monospace"
        "--font" "TITLE:13:Monospace"
        "--font" "LEGEND:10:Monospace"
        "--font" "AXIS:9:Monospace"    
        )

    CONTADOR=0
    RRDDATE="" # Inicializamos variable
    
    gen_color() { printf "#%06x" $((RANDOM * RANDOM % 0xFFFFFF)); }

    # Leemos JSON
    while read -r name; do
        RRD_FILE="$DIR_RRD/$name.rrd"
        SAFE_NAME=${name//-/_}

        IDX=$((CONTADOR % 10))
        COLOR=${COLORES[$IDX]}
        
        RRDDATE=$(rrdtool last "$RRD_FILE" | xargs -I {} date -d @{} "+%d/%m/%Y %H\:%M\:%S")

        # DEF y CDEF
        OPTS+=("DEF:raw_$SAFE_NAME=$RRD_FILE:$TIPO:AVERAGE")
        
        if (( $(echo "$TOTAL > 0" | bc -l) )); then
             OPTS+=("CDEF:$SAFE_NAME=raw_$SAFE_NAME,$TOTAL,/,100,*")
        else
             OPTS+=("CDEF:$SAFE_NAME=raw_$SAFE_NAME,0,*")
        fi

        # DIBUJO y LEYENDA (TABLA)
        MODO="STACK"
        [ $CONTADOR -eq 0 ] && MODO="AREA"
        
        LABEL_PADDED=$(printf "%-20s" "${name:0:20}")
        
        OPTS+=("$MODO:$SAFE_NAME$COLOR:$LABEL_PADDED")
        OPTS+=("GPRINT:$SAFE_NAME:LAST:Cur\:%6.2lf%%")
        OPTS+=("GPRINT:$SAFE_NAME:AVERAGE: Avg\:%6.2lf%%")
        OPTS+=("GPRINT:$SAFE_NAME:MAX: Max\:%6.2lf%%\\n")
        
        ((CONTADOR++))
    done < <(echo "$JSON_DATA" | jq -r '.[] | .name')

    # Footer
    OPTS+=("COMMENT: \\n")
    # Usamos la variable capturada con tu método
    OPTS+=("COMMENT:Last data update\: $RRDDATE\r")

    rrdtool "${OPTS[@]}" >/dev/null
    echo "Gráfica generada: $OUT_IMG"
    rrdtool "${OPTS[@]}" >/dev/null
    echo "Gráfica generada: $OUT_IMG"
}

generar_grafica_red() {
    PERIODO=$1
    TITULO="Traefik Global RPS - $PERIODO"
    OUT_IMG="$DIR_RRD/graph_net_${PERIODO}.png"
    RRD_FILE="$DIR_RRD/traefik-global-requests.rrd"

    # Si no existe aun el rrd de red, salir
    [ ! -f "$RRD_FILE" ] && return

    rrdtool graph "$OUT_IMG" \
        --start "-1$PERIODO" \
        -w "$ANCHO" -h "$ALTO" -a PNG --slope-mode \
        --title "$TITULO" \
        --vertical-label "Req / Sec" \
        --lower-limit 0 \
        --color "CANVAS#000000" --color "FONT#FFFFFF" --color "BACK#000000" \
        DEF:req=$RRD_FILE:requests:AVERAGE \
        AREA:req#3380FF:"Total Requests" \
        GPRINT:req:LAST:"Cur\: %6.2lf RPS" \
        GPRINT:req:AVERAGE:"Avg\: %6.2lf RPS" \
        GPRINT:req:MAX:"Max\: %6.2lf RPS\n" >/dev/null

    echo "Gráfica Red generada: $OUT_IMG"
}

# 4. EJECUCIÓN
for p in day week month year; do
    generar_grafica "cpu" "$TOTAL_CPU_CORES" "$p"
    generar_grafica "mem" "$TOTAL_MEM_MIB" "$p"
    generar_grafica_red "$p"
done