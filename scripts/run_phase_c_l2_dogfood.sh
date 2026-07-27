#!/usr/bin/env bash
# Phase C / C1 — N4-D3 L2 sample fill (live supervisor).
# Needs: live agents, API :8765 with x2-lift env + AGENT_LAB_PLAN_INBOX=1.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COUNT="${COUNT:-10}"
ALLOW_DIRTY="${ALLOW_DIRTY:-0}"

echo "=== Phase C L2 dogfood (N4-D3) ==="
echo "count=$COUNT  API=${AGENT_LAB_API:-http://127.0.0.1:8765}"

# Shell-side env for CLI helpers; API must already have inherited these.
eval "$(make -s x2-lift-dogfood-env)"
export AGENT_LAB_PLAN_INBOX=1

READY="$(curl -sf "${AGENT_LAB_API:-http://127.0.0.1:8765}/api/health/readiness" || true)"
if [[ -z "$READY" ]]; then
  echo "API not ready. Start with:" >&2
  echo "  eval \"\$(make -s x2-lift-dogfood-env)\"" >&2
  echo "  export AGENT_LAB_PLAN_INBOX=1" >&2
  echo "  make api" >&2
  exit 1
fi

FLAGS="$(curl -sf "${AGENT_LAB_API:-http://127.0.0.1:8765}/api/health/flags")"
AGENT_LAB_FLAGS_JSON="$FLAGS" .venv/bin/python - <<'PY'
import json, os, sys
flags = {f["name"]: f for f in json.loads(os.environ["AGENT_LAB_FLAGS_JSON"]).get("flags") or []}
ei = flags.get("AGENT_LAB_EXECUTE_INBOX") or {}
pi = flags.get("AGENT_LAB_PLAN_INBOX") or {}
eff_ei = str(ei.get("effective") or "").lower()
eff_pi = str(pi.get("effective") or "").lower()
print(
    f"EXECUTE_INBOX effective={ei.get('effective')!r}  "
    f"PLAN_INBOX effective={pi.get('effective')!r}"
)
if eff_ei not in {"0", "off", "false", "no"}:
    raise SystemExit(
        "API must run with AGENT_LAB_EXECUTE_INBOX=0 (restart after x2-lift-dogfood-env)"
    )
if eff_pi not in {"1", "on", "true", "yes"}:
    raise SystemExit(
        "API must run with AGENT_LAB_PLAN_INBOX=1 (HUMAN_PENDING ask_human)"
    )
PY

ARGS=(--count "$COUNT")
if [[ "$ALLOW_DIRTY" == "1" ]]; then
  ARGS+=(--allow-dirty)
fi

.venv/bin/python scripts/l2_escalation_dogfood_live_repeat.py "${ARGS[@]}"
echo "=== re-check N4 gate ==="
make dogfood-track
