#!/usr/bin/env bash
# Automated browser DOM smoke. Kept separate from the manual Tauri real-window smoke.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARTIFACT_DIR="${AGENT_LAB_UI_ARTIFACT_DIR:-/tmp/agent-lab-ui-smoke/web}"
LOG_PATH="$ARTIFACT_DIR/dev-server.log"
API_LOG_PATH="$ARTIFACT_DIR/api-server.log"
API_PID=""
SERVER_PID=""
CODEX_NODE_BIN="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
NODE_BIN="${NODE:-}"
NPM_BIN="$(command -v npm || true)"

port_in_use() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

listener_pid() {
  lsof -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null | head -n 1
}

kill_tree() {
  local pid="$1"
  local child
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    kill_tree "$child"
  done
  kill -TERM "$pid" 2>/dev/null || true
}

cleanup() {
  if [[ -n "$API_PID" ]]; then
    kill_tree "$API_PID"
    wait "$API_PID" 2>/dev/null || true
  fi
  if [[ -n "$SERVER_PID" ]]; then
    kill_tree "$SERVER_PID"
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

cd "$ROOT"
mkdir -p "$ARTIFACT_DIR"

if [[ -z "$NODE_BIN" && -x "$CODEX_NODE_BIN" ]]; then
  NODE_BIN="$CODEX_NODE_BIN"
fi
if [[ -z "$NODE_BIN" ]]; then
  NODE_BIN="$(command -v node || true)"
fi

if [[ ! -x .venv/bin/python || ! -d web/node_modules/playwright || -z "$NODE_BIN" ]]; then
  echo "Run: make install && cd web && npm install" >&2
  exit 1
fi
if port_in_use 8765 || port_in_use 5173; then
  echo "smoke-web-ui requires free ports 8765 and 5173 so it can serve the isolated fixture." >&2
  exit 1
fi

.venv/bin/python scripts/verify_ui_smoke_fixture.py
echo "Web smoke log: $LOG_PATH"
echo "API smoke log: $API_LOG_PATH"

env -i \
  HOME="$HOME" \
  PATH="$PATH" \
  TMPDIR="${TMPDIR:-/tmp}" \
  AGENT_LAB_SESSIONS_DIR="$ROOT/sessions/_regression" \
  AGENT_LAB_MOCK_AGENTS=1 \
  "$ROOT/.venv/bin/uvicorn" app.server.main:app \
    --host 127.0.0.1 \
    --port 8765 \
    >"$API_LOG_PATH" 2>&1 &
API_PID=$!

for _ in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "API server exited; inspect $API_LOG_PATH" >&2
    exit 1
  fi
  sleep 0.4
done
curl -fsS http://127.0.0.1:8765/api/health >/dev/null

if [[ -n "$NPM_BIN" ]]; then
  AGENT_LAB_SESSIONS_DIR="$ROOT/sessions/_regression" \
  AGENT_LAB_MOCK_AGENTS=1 \
  "$NPM_BIN" --prefix "$ROOT/web" run dev -- --host 127.0.0.1 --port 5173 --strictPort \
    >"$LOG_PATH" 2>&1 &
else
  (
    cd "$ROOT/web"
    AGENT_LAB_SESSIONS_DIR="$ROOT/sessions/_regression" \
    AGENT_LAB_MOCK_AGENTS=1 \
    "$NODE_BIN" node_modules/.bin/vite --host 127.0.0.1 --port 5173 --strictPort
  ) >"$LOG_PATH" 2>&1 &
fi
SERVER_PID=$!

for _ in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:5173 >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    LISTENER_PID="$(listener_pid 5173)"
    if [[ -n "$LISTENER_PID" ]]; then
      SERVER_PID="$LISTENER_PID"
    else
      echo "Web dev server exited; inspect $LOG_PATH" >&2
      exit 1
    fi
  fi
  sleep 0.4
done

curl -fsS http://127.0.0.1:5173 >/dev/null
.venv/bin/python scripts/verify_ui_smoke_fixture.py --api-base http://127.0.0.1:8765

AGENT_LAB_WEB_URL=http://127.0.0.1:5173 \
AGENT_LAB_UI_ARTIFACT_DIR="$ARTIFACT_DIR" \
"$NODE_BIN" scripts/smoke_web_ui.mjs
