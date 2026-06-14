#!/usr/bin/env bash
# CC-hooks PostEdit: ruff lint report on edited Python files (dev-tool only).
# Report-only — never silently rewrites source (no --fix) and never blocks the
# edit. The enforcing gate is `ruff check` in CI; this is just a fast local heads-up.
set -euo pipefail
file="${CLAUDE_EDITED_FILE:-}"
[[ -z "$file" || "$file" != *.py ]] && exit 0
root="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -x "$root/.venv/bin/ruff" ]]; then
  "$root/.venv/bin/ruff" check "$file" || true
fi
