#!/usr/bin/env bash
# Automated browser DOM smoke. Kept separate from the manual Tauri real-window smoke.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARTIFACT_DIR="${AGENT_LAB_UI_ARTIFACT_DIR:-/tmp/agent-lab-ui-smoke/web}"
LOG_PATH="$ARTIFACT_DIR/dev-server.log"
SERVER_PID=""

port_in_use() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
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
  if [[ -n "$SERVER_PID" ]]; then
    kill_tree "$SERVER_PID"
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

cd "$ROOT"
mkdir -p "$ARTIFACT_DIR"

if [[ ! -x .venv/bin/python || ! -d web/node_modules/playwright ]]; then
  echo "Run: make install && cd web && npm install" >&2
  exit 1
fi
if port_in_use 8765 || port_in_use 5173; then
  echo "smoke-web-ui requires free ports 8765 and 5173 so it can serve the isolated fixture." >&2
  exit 1
fi

.venv/bin/python scripts/verify_ui_smoke_fixture.py
echo "Web smoke log: $LOG_PATH"
AGENT_LAB_SESSIONS_DIR="$ROOT/sessions/_regression" \
AGENT_LAB_MOCK_AGENTS=1 \
npm --prefix "$ROOT/web" run dev -- --host 127.0.0.1 --port 5173 --strictPort \
  >"$LOG_PATH" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:5173 >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "Web dev server exited; inspect $LOG_PATH" >&2
    exit 1
  fi
  sleep 0.4
done

curl -fsS http://127.0.0.1:5173 >/dev/null
.venv/bin/python scripts/verify_ui_smoke_fixture.py --api-base http://127.0.0.1:8765

AGENT_LAB_WEB_URL=http://127.0.0.1:5173 \
AGENT_LAB_UI_ARTIFACT_DIR="$ARTIFACT_DIR" \
node scripts/smoke_web_ui.mjs
