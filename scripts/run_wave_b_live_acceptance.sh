#!/usr/bin/env bash
# Wave B live browser acceptance — seed + real API + Playwright (no API mocks).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SESSIONS_DIR="${WAVE_B_LIVE_SESSIONS_DIR:-$(mktemp -d /tmp/wave-b-live.XXXXXX)}"
API_PORT="${WAVE_B_LIVE_API_PORT:-18765}"
UI_PORT="${WAVE_B_LIVE_UI_PORT:-4173}"
API_PID=""
cleanup() {
  if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
    kill "${API_PID}" 2>/dev/null || true
    wait "${API_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "==> seeding sessions into ${SESSIONS_DIR}"
.venv/bin/python scripts/seed_wave_b_live_sessions.py --sessions-dir "${SESSIONS_DIR}"

echo "==> starting API on :${API_PORT}"
export AGENT_LAB_SESSIONS_DIR="${SESSIONS_DIR}"
export AGENT_LAB_MOCK_AGENTS=1
export AGENT_LAB_MISSION_UI_READ_MODEL=1
export AGENT_LAB_MISSION_AUTHORITY=1
export AGENT_LAB_MISSION_AUTHORITY_SESSIONS=wave-b-live-human-resume
export PYTHONPATH="${ROOT}/src:${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

.venv/bin/python -m uvicorn app.server.main:app --host 127.0.0.1 --port "${API_PORT}" \
  >/tmp/wave-b-live-api.log 2>&1 &
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

echo "==> Playwright live journeys (UI :${UI_PORT} → API :${API_PORT})"
cd web
export VITE_API_PROXY_TARGET="http://127.0.0.1:${API_PORT}"
npx playwright test e2e/wave-b-live-journey.spec.ts \
  --config=playwright.wave-b-live.config.ts

echo "==> WAVE_B_LIVE_ACCEPTANCE: PASS"
echo "sessions_dir=${SESSIONS_DIR}"
echo "api_log=/tmp/wave-b-live-api.log"
