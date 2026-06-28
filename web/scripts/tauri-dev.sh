#!/usr/bin/env bash
# Tauri beforeDevCommand — API is started by Vite plugin (ensure-dev-api.mjs).
set -euo pipefail
cd "$(dirname "$0")/.."
export AGENT_LAB_SKIP_TAURI_API=1

VITE_PORT=1420

stop_stale_port() {
  local port="$1"
  if ! lsof -ti "tcp:${port}" >/dev/null 2>&1; then
    return 0
  fi
  echo "[agent-lab] Port ${port} is in use — stopping stale Vite listener"
  lsof -ti "tcp:${port}" | xargs kill -9 2>/dev/null || true
  sleep 0.5
  if lsof -ti "tcp:${port}" >/dev/null 2>&1; then
    echo "[agent-lab] Port ${port} still in use. Run: kill \$(lsof -ti:${port})" >&2
    exit 1
  fi
}

stop_stale_api_port() {
  if ! lsof -ti "tcp:8765" >/dev/null 2>&1; then
    return 0
  fi
  if curl -sf --max-time 2 "http://127.0.0.1:8765/api/health" >/dev/null 2>&1; then
    echo "[agent-lab] API already healthy on :8765"
    return 0
  fi
  echo "[agent-lab] Port 8765 is open but API unhealthy — stopping stale listener"
  lsof -ti "tcp:8765" | xargs kill -9 2>/dev/null || true
  pkill -9 -f "uvicorn app.server.main:app" 2>/dev/null || true
  sleep 0.5
}

stop_stale_port "${VITE_PORT}"
stop_stale_api_port

echo "Vite → http://127.0.0.1:${VITE_PORT} (API auto-starts on :8765 before Vite is ready)"
exec npx vite --port "${VITE_PORT}" --strictPort --host 127.0.0.1
