#!/usr/bin/env bash
# Tauri beforeDevCommand — API is started by Vite plugin (ensure-dev-api.mjs).
set -euo pipefail
cd "$(dirname "$0")/.."
export AGENT_LAB_SKIP_TAURI_API=1
echo "Vite → http://127.0.0.1:1420 (API auto-starts on :8765 via vite plugin)"
exec npx vite --port 1420 --strictPort --host 127.0.0.1
