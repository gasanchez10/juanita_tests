#!/usr/bin/env bash
# Arranca TikTok Pulse y abre el Swagger:  ./iniciar.sh   (Ctrl+C para detener)
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "❌ Falta la instalación. Corre primero: ./instalar.sh"
  exit 1
fi

PORT="${PORT:-8000}"
URL="http://localhost:$PORT/docs"
echo "== TikTok Pulse en $URL  (Ctrl+C para detener) =="

( sleep 3; if command -v open >/dev/null 2>&1; then open "$URL"; elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"; fi ) >/dev/null 2>&1 &
exec .venv/bin/python -m uvicorn tiktok_agent.api:app --port "$PORT"
