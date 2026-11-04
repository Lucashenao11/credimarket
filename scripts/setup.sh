#!/bin/bash
# Genera los secretos locales la primera vez: .env y el par de llaves RSA para los JWT.
# Uso (desde la raíz del repositorio):  ./scripts/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then
  echo ".env ya existe; no se modifica."
else
  while IFS= read -r linea; do
    if [[ "$linea" =~ ^([A-Z_]+)=cambiar$ ]]; then
      echo "${BASH_REMATCH[1]}=$(openssl rand -hex 24)"
    else
      echo "$linea"
    fi
  done < .env.example > .env
  echo ".env creado con contraseñas aleatorias."
fi

mkdir -p secrets
if [ -f secrets/jwt_private.pem ] && [ -f secrets/jwt_public.pem ]; then
  echo "Las llaves JWT ya existen; no se modifican."
else
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out secrets/jwt_private.pem
  openssl rsa -in secrets/jwt_private.pem -pubout -out secrets/jwt_public.pem
  echo "Llaves JWT creadas en secrets/."
fi
echo "Listo. Ahora ejecuta: docker compose up --build"
