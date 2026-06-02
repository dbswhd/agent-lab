#!/usr/bin/env bash
# pre_execute hook — exit 2 to block plan dry-run before Cursor snapshot.
set -euo pipefail
payload="$(cat)"
if command -v python3 >/dev/null 2>&1; then
  python3 -c '
import json, sys
d = json.load(sys.stdin)
action = d.get("action") or {}
what = (action.get("what") or "").strip()
if what.upper().startswith("BLOCK_PRE_EXECUTE"):
    print("pre_execute regression block", file=sys.stderr)
    sys.exit(2)
' <<<"$payload"
fi
exit 0
