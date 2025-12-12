#!/bin/bash
# entrypoint.sh

# Salvar variables de entorno para que cron pueda verlas
# Usamos un formato simple export VAR="VAL"
env | sed 's/^\(.*\)=\(.*\)$/export \1="\2"/' > /app/environment.sh

# Ejecutar el comando original (CMD en Dockerfile)
exec "$@"
