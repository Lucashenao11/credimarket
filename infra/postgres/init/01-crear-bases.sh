#!/bin/bash
# Se ejecuta solo la primera vez que se crea el volumen de PostgreSQL.
# Crea una base de datos y un usuario por servicio. Cada usuario es dueño
# únicamente de su base y no puede conectarse a las bases de los demás.
set -euo pipefail

crear_base() {
  local nombre="$1"
  local password="$2"
  echo ">> Creando base y usuario: ${nombre}"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-SQL
    CREATE ROLE ${nombre} LOGIN PASSWORD '${password}';
    CREATE DATABASE ${nombre} OWNER ${nombre};
    REVOKE ALL ON DATABASE ${nombre} FROM PUBLIC;
    GRANT CONNECT, TEMPORARY ON DATABASE ${nombre} TO ${nombre};
SQL
}

crear_base productos  "$PRODUCTOS_DB_PASSWORD"
crear_base clientes   "$CLIENTES_DB_PASSWORD"
crear_base prestamos  "$PRESTAMOS_DB_PASSWORD"
crear_base inventario "$INVENTARIO_DB_PASSWORD"
crear_base mlflow     "$MLFLOW_DB_PASSWORD"

# La base "postgres" tampoco debe ser accesible para los usuarios de servicio.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -c "REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;"

echo ">> Bases de datos creadas con aislamiento por usuario."
