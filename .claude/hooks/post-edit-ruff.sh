#!/usr/bin/env bash
# CC-hooks PostEdit: ruff --fix on edited Python files (dev-tool only).
set -euo pipefail
file="${CLAUDE_EDITED_FILE:-}"
[[ -z "$file" || "$file" != *.py ]] && exit 0
root="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -x "$root/.venv/bin/ruff" ]]; then
  "$root/.venv/bin/ruff" check --fix "$file" 2>/dev/null || true
fi
