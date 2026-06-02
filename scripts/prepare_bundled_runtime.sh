#!/usr/bin/env bash
# Build a relocatable Python venv for the Tauri release bundle.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE_DIR="$ROOT/web/src-tauri/bundled-runtime"
VENV="$BUNDLE_DIR/venv"

resolve_bundle_python() {
  if [[ -n "${AGENT_LAB_BUNDLE_PYTHON:-}" ]]; then
    echo "$AGENT_LAB_BUNDLE_PYTHON"
    return
  fi
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    echo "$ROOT/.venv/bin/python"
    return
  fi
  for c in python3.13 python3.12 python3.11 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      command -v "$c"
      return
    fi
  done
  echo "python3"
}

PYTHON="$(resolve_bundle_python)"
echo "Preparing bundled Python runtime at $VENV"
echo "Using interpreter: $PYTHON ($("$PYTHON" --version 2>&1))"

"$PYTHON" -c 'import sys; v=sys.version_info[:2]; assert v>=(3,11), f"need Python >=3.11, got {sys.version}"'

rm -rf "$VENV"
# --copies: embed python binary so the venv survives copy into Agent Lab.app
"$PYTHON" -m venv --copies "$VENV"
"$VENV/bin/pip" install -q -U pip wheel
"$VENV/bin/pip" install -q -e "$ROOT[cursor]"

"$VENV/bin/python" -c "import cursor_sdk  # noqa: F401"
"$VENV/bin/python" -c "import app.server.main  # noqa: F401"

# Relocation smoke: mimic Tauri copying venv into .app Resources
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp -R "$VENV" "$TMP/venv"
(
  cd "$ROOT"
  AGENT_LAB_ROOT="$ROOT" "$TMP/venv/bin/python" -c "import app.server.main"
)
echo "Bundled runtime OK (relocatable smoke passed, $("$VENV/bin/python" --version))"
