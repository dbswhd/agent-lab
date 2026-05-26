#!/usr/bin/env bash
# Vite on 1420 for `tauri dev`. API is started by src-tauri Rust on port 8765.
set -euo pipefail
cd "$(dirname "$0")/.."
exec npx vite --port 1420 --strictPort
