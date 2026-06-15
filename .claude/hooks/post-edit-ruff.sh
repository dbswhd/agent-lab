#!/usr/bin/env bash
# CC-hooks PostToolUse: ruff lint report on edited Python files (dev-tool only).
# Report-only — never silently rewrites source (no --fix) and never blocks the edit.
set -euo pipefail

file=""
if [[ ! -t 0 ]]; then
  file=$(jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null || true)
fi
file="${file:-${CLAUDE_EDITED_FILE:-}}"
[[ -z "$file" || "$file" != *.py ]] && exit 0

root="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -x "$root/.venv/bin/ruff" ]]; then
  "$root/.venv/bin/ruff" check "$file" || true
fi
