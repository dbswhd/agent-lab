#!/usr/bin/env bash
# Start API (8765) + Vite web (5173). Requires: .venv + npm install in web/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Run: python3 -m venv .venv && .venv/bin/pip install -e ."
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if [[ ! -d web/node_modules ]]; then
  echo "Run: cd web && npm install"
  exit 1
fi

echo "API  → http://127.0.0.1:8765"
echo "Web  → http://127.0.0.1:5173"
uvicorn app.server.main:app --reload --host 127.0.0.1 --port 8765 \
  --reload-dir app --reload-dir src --reload-dir tests &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT

(cd web && VITE_SKIP_API=1 npm run dev) &
WEB_PID=$!
trap 'kill $API_PID $WEB_PID 2>/dev/null || true' EXIT

wait $WEB_PID
