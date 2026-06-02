#!/usr/bin/env bash
# Release checklist: bundled .app resources + optional live API probe.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_APP="$ROOT/web/src-tauri/target/release/bundle/macos/Agent Lab.app"
APP_PATH="${1:-$DEFAULT_APP}"
SKIP_API="${VERIFY_RELEASE_SKIP_API:-0}"
API_URL="${VERIFY_RELEASE_API_URL:-http://127.0.0.1:8765}"
FAIL=0

say_ok() { echo "OK: $*"; }
say_fail() { echo "FAIL: $*" >&2; FAIL=1; }

if [[ ! -d "$APP_PATH" ]]; then
  say_fail "App bundle not found: $APP_PATH"
  say_fail "Build first: make tauri-build  (or pass path to .app)"
  exit 1
fi

RESOURCES="$APP_PATH/Contents/Resources"
RUNTIME="$RESOURCES/runtime"

if [[ ! -d "$RUNTIME" ]]; then
  say_fail "Missing Resources/runtime in bundle"
  exit 1
fi

PYTHON=""
for candidate in \
  "$RUNTIME/venv/bin/python3" \
  "$RUNTIME/venv/bin/python" \
  "$RUNTIME/.venv/bin/python3" \
  "$RUNTIME/.venv/bin/python"; do
  if [[ -x "$candidate" ]]; then
    PYTHON="$candidate"
    break
  fi
done

if [[ -z "$PYTHON" ]]; then
  say_fail "Bundled Python not found under $RUNTIME/venv/bin"
else
  say_ok "bundled python: $PYTHON"
  if AGENT_LAB_ROOT="$RUNTIME" "$PYTHON" -c "import app.server.main" 2>/dev/null; then
    say_ok "import app.server.main"
  else
    say_fail "cannot import app.server.main (AGENT_LAB_ROOT=$RUNTIME)"
  fi
fi

BRIDGE_FOUND=0
for bridge in \
  "$RUNTIME/venv/bin/cursor-sdk-bridge" \
  "$RUNTIME/venv/bin/cursor_sdk_bridge"; do
  if [[ -e "$bridge" ]]; then
    say_ok "cursor-sdk-bridge: $bridge"
    BRIDGE_FOUND=1
    break
  fi
done
if [[ "$BRIDGE_FOUND" -eq 0 ]]; then
  # Wheel may ship native launcher only — check import path.
  if [[ -n "$PYTHON" ]] && AGENT_LAB_ROOT="$RUNTIME" "$PYTHON" -c "
from cursor_sdk._vendor import _bundled_launcher_path, resolve_bridge_path
p = _bundled_launcher_path() or resolve_bridge_path()
assert p
" 2>/dev/null; then
    say_ok "cursor-sdk bridge via cursor_sdk vendor"
    BRIDGE_FOUND=1
  fi
fi
if [[ "$BRIDGE_FOUND" -eq 0 ]]; then
  say_fail "cursor-sdk-bridge not found in bundle (venv/bin or cursor_sdk vendor)"
fi

if [[ -d "$RUNTIME/web/dist" ]]; then
  say_ok "runtime/web/dist present"
else
  say_fail "missing runtime/web/dist (run npm run build before tauri build)"
fi

if [[ "$SKIP_API" == "1" ]]; then
  echo "SKIP: live API probe (VERIFY_RELEASE_SKIP_API=1)"
else
  if curl -sf --max-time 3 "$API_URL/api/health" >/dev/null 2>&1; then
    say_ok "GET /api/health"
    if curl -sf --max-time 3 "$API_URL/api/sessions" >/dev/null 2>&1; then
      say_ok "GET /api/sessions"
    else
      say_fail "GET /api/sessions (is API running at $API_URL?)"
      echo "Hint: start app or \`make dev\`, or VERIFY_RELEASE_SKIP_API=1"
    fi
  else
    say_fail "GET /api/health (API offline at $API_URL)"
    echo "Hint: launch Agent Lab.app or \`make dev\`; or VERIFY_RELEASE_SKIP_API=1"
  fi
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo ""
  echo "Release verification failed. / 릴리스 검증 실패."
  exit 1
fi

echo ""
echo "Release verification passed. / 릴리스 검증 통과."
exit 0
