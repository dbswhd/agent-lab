#!/usr/bin/env bash
# Phase B Small Mission dogfood — B1–B4 surfaces on real API + Vite.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SESSIONS_DIR="${PHASE_B_SESSIONS_DIR:-$(mktemp -d /tmp/phase-b-small.XXXXXX)}"
API_PORT="${PHASE_B_API_PORT:-18768}"
UI_PORT="${PHASE_B_UI_PORT:-4174}"
API_PID=""
cleanup() {
  if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
    kill "${API_PID}" 2>/dev/null || true
    wait "${API_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "==> seeding Small Mission dogfood into ${SESSIONS_DIR}"
.venv/bin/python scripts/seed_phase_b_small_mission_dogfood.py --sessions-dir "${SESSIONS_DIR}"

echo "==> starting API on :${API_PORT} (profile=small)"
export AGENT_LAB_SESSIONS_DIR="${SESSIONS_DIR}"
export AGENT_LAB_MOCK_AGENTS=1
export AGENT_LAB_RUN_PROFILE=small
export AGENT_LAB_MISSION_BUDGET_USD=5
export AGENT_LAB_MISSION_UI_READ_MODEL=1
export PYTHONPATH="${ROOT}/src:${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

.venv/bin/python -m uvicorn app.server.main:app --host 127.0.0.1 --port "${API_PORT}" \
  >/tmp/phase-b-small-api.log 2>&1 &
API_PID=$!

echo "==> waiting for API"
for _ in $(seq 1 120); do
  if curl -sf "http://127.0.0.1:${API_PORT}/api/health" >/dev/null; then
    echo "API up"
    break
  fi
  sleep 0.5
done
curl -sf "http://127.0.0.1:${API_PORT}/api/health" >/dev/null

echo "==> API smoke: runtime human_gate + score latency"
curl -sf "http://127.0.0.1:${API_PORT}/api/sessions/phase-b-small-gate/runtime" \
  | .venv/bin/python -c "
import sys, json
d=json.load(sys.stdin)
line=d.get('status_line') or {}
assert line.get('run_profile')=='small', line
assert line.get('human_gate_opened_at'), line
assert line.get('human_gate_kind')=='plan_approval', line
print('runtime_ok', line.get('run_profile'), line.get('human_gate_kind'))
"
.venv/bin/python - <<PY
from pathlib import Path
from agent_lab.session.score import score_session
folder = Path("${SESSIONS_DIR}") / "phase-b-small-gate"
scores = score_session(folder)["scores"]
assert scores.get("decision_latency_open") == 1.0, scores
print("score_ok", {k: scores[k] for k in scores if k.startswith("decision_latency")})
PY

echo "==> Playwright Phase B surfaces (UI :${UI_PORT} → API :${API_PORT})"
cd web
export VITE_API_PROXY_TARGET="http://127.0.0.1:${API_PORT}"
export PHASE_B_UI_PORT="${UI_PORT}"
npx playwright test e2e/phase-b-small-mission-dogfood.spec.ts \
  --config=playwright.phase-b-small.config.ts

echo "==> PHASE_B_SMALL_MISSION_DOGFOOD: PASS"
echo "sessions_dir=${SESSIONS_DIR}"
echo "api_log=/tmp/phase-b-small-api.log"
