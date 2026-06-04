#!/usr/bin/env bash
# Manual macOS real-window smoke for the P0 pending dry-run diff scenario.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARTIFACT_DIR="${AGENT_LAB_UI_ARTIFACT_DIR:-/tmp/agent-lab-ui-smoke/tauri}"
LOG_PATH="$ARTIFACT_DIR/tauri-dev.log"
TAURI_PID=""

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
  if [[ -n "$TAURI_PID" ]]; then
    kill_tree "$TAURI_PID"
    wait "$TAURI_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

cd "$ROOT"
mkdir -p "$ARTIFACT_DIR"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "smoke-tauri-ui requires macOS." >&2
  exit 1
fi
if [[ ! -x .venv/bin/python || ! -d web/node_modules ]]; then
  echo "Run: make install" >&2
  exit 1
fi
if port_in_use 8765 || port_in_use 1420; then
  echo "smoke-tauri-ui requires free ports 8765 and 1420 so it can serve the isolated fixture." >&2
  exit 1
fi
if pgrep -f "$ROOT/web/src-tauri/target/debug/agent-lab-app" >/dev/null 2>&1; then
  echo "A repo-local Agent Lab Tauri process is already running; stop it before this smoke." >&2
  exit 1
fi

.venv/bin/python scripts/verify_ui_smoke_fixture.py
echo "Tauri smoke log: $LOG_PATH"
AGENT_LAB_SESSIONS_DIR="$ROOT/sessions/_regression" \
AGENT_LAB_MOCK_AGENTS=1 \
make tauri-dev >"$LOG_PATH" 2>&1 &
TAURI_PID=$!

for _ in $(seq 1 150); do
  if curl -fsS http://127.0.0.1:8765/api/health >/dev/null 2>&1 &&
    osascript -e 'tell application "System Events" to tell process "agent-lab-app" to count windows' 2>/dev/null |
      grep -Eq '^[1-9][0-9]*$'; then
    break
  fi
  if ! kill -0 "$TAURI_PID" 2>/dev/null; then
    echo "Tauri dev process exited; inspect $LOG_PATH" >&2
    exit 1
  fi
  sleep 0.4
done

.venv/bin/python scripts/verify_ui_smoke_fixture.py --api-base http://127.0.0.1:8765
osascript -e 'tell application "System Events" to tell process "agent-lab-app" to set frontmost to true'

cat <<'STEPS'

Tauri real-window scenario:
  1. Select “P0 UI smoke · pending dry-run diff” in the session list.
  2. Open the “plan · 승인” tab.
  3. Confirm the “승인 대기” region exposes an open “로컬 diff”.
  4. Confirm the diff contains “P0_UI_DIFF_MARKER”.

STEPS

if [[ "${AGENT_LAB_TAURI_UI_SMOKE_LAUNCH_ONLY:-0}" == "1" ]]; then
  echo "LAUNCH-ONLY: real window and fixture API verified; visual operator confirmation skipped."
  exit 0
fi
if [[ ! -t 0 ]]; then
  echo "FAIL: visual confirmation requires an interactive terminal." >&2
  exit 2
fi

read -r -p "Did the real window pass all four checks? [y/N] " answer
case "$answer" in
  y|Y|yes|YES)
    echo "OK: Tauri real-window pending dry-run diff scenario"
    ;;
  *)
    echo "FAIL: Tauri real-window pending dry-run diff scenario" >&2
    exit 1
    ;;
esac
