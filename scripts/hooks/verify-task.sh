#!/usr/bin/env bash
# task_completed hook — exit 2 to block Human/agent task complete.
set -euo pipefail
payload="$(cat)"
# Example: require task title non-empty (always passes). Replace with pytest/lint.
if command -v python3 >/dev/null 2>&1; then
  python3 -c '
import json, sys
d = json.load(sys.stdin)
t = d.get("task") or {}
if not (t.get("title") or "").strip():
    print("task title missing", file=sys.stderr)
    sys.exit(2)
' <<<"$payload"
fi
exit 0
