#!/usr/bin/env bash
# Instala TikTok Pulse en Mac o Linux:  ./instalar.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "== TikTok Pulse · instalación =="

PY=""
for cand in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    PY="$cand"; break
  fi
done
if [ -z "$PY" ]; then
  echo "❌ Necesitas Python 3.10 o superior. Instálalo desde https://www.python.org/downloads/ y vuelve a correr este script."
  exit 1
fi
echo "✅ Usando $($PY --version)"

if [ ! -d .venv ]; then
  echo "→ Creando entorno virtual .venv"
  "$PY" -m venv .venv
fi
echo "→ Instalando dependencias (1–2 minutos)"
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "⚠️  Se creó el archivo .env. Ábrelo con un editor de texto y llena tus llaves:"
  echo "    APIFY_TOKEN y OPENAI_API_KEY (o las variables AZURE_OPENAI_*)."
  echo "    Mientras tanto puedes probar con modo_prueba: true (sin costo)."
fi

echo
echo "== Diagnóstico =="
.venv/bin/python run.py doctor || true
echo
echo "Siguiente paso: ./iniciar.sh  (abre el Swagger en el navegador)"
