#!/usr/bin/env bash
# CC-hooks PostEdit: prettier on edited TSX files (dev-tool only).
set -euo pipefail
file="${CLAUDE_EDITED_FILE:-}"
[[ -z "$file" || "$file" != *.tsx ]] && exit 0
root="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -d "$root/web/node_modules" ]]; then
  (cd "$root/web" && npx prettier --write "$file" 2>/dev/null) || true
fi
