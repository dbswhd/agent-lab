#!/usr/bin/env bash
# Verify Tauri native folder picker wiring (static + cargo check).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "OK: $*"; }

grep -q 'tauri-plugin-dialog' web/src-tauri/Cargo.toml \
  || fail "Cargo.toml missing tauri-plugin-dialog"
grep -q 'tauri_plugin_dialog::init' web/src-tauri/src/lib.rs \
  || fail "lib.rs missing dialog plugin init"
grep -q '@tauri-apps/plugin-dialog' web/package.json \
  || fail "package.json missing @tauri-apps/plugin-dialog"
grep -q 'dialog:default' web/src-tauri/capabilities/default.json \
  || fail "capabilities missing dialog:default"
grep -q 'pickWorkspaceFolder' web/src/utils/pickWorkspaceFolder.ts \
  || fail "pickWorkspaceFolder missing"
grep -q 'plugin-dialog' web/src/utils/pickWorkspaceFolder.ts \
  || fail "pickWorkspaceFolder must import @tauri-apps/plugin-dialog"

ok "static config — dialog plugin wired"

(cd web/src-tauri && cargo check -q 2>&1) || fail "cargo check failed"
ok "cargo check — tauri-plugin-dialog + rfd linked"

echo "verify_tauri_dialog: all checks passed"
