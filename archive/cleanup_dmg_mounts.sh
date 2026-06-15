#!/usr/bin/env bash
# Detach stale create-dmg interstitial volumes and remove rw.*.dmg temp files.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE_MACOS="$ROOT/web/src-tauri/target/release/bundle/macos"

if ! command -v hdiutil >/dev/null 2>&1; then
  exit 0
fi

while IFS= read -r dev; do
  [[ -z "$dev" ]] && continue
  echo "cleanup_dmg_mounts: detaching $dev"
  hdiutil detach "$dev" -force >/dev/null 2>&1 || true
done < <(hdiutil info 2>/dev/null | awk '/\/Volumes\/dmg\./ {print $1}')

if [[ -d "$BUNDLE_MACOS" ]]; then
  find "$BUNDLE_MACOS" -maxdepth 1 -name 'rw.*.dmg' -delete 2>/dev/null || true
fi
