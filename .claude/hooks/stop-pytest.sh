#!/usr/bin/env bash
# CC-hooks Stop: quick pytest tail on agent stop (dev-tool only).
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"

if [[ "${AGENT_LAB_SKIP_STOP_PYTEST:-0}" = "1" ]]; then
  exit 0
fi

lock_dir="${TMPDIR:-/tmp}/agent-lab-stop-pytest.lock"
if ! mkdir "$lock_dir" 2>/dev/null; then
  echo "stop-pytest: skipped; another pytest hook is running"
  exit 0
fi
trap 'rmdir "$lock_dir" 2>/dev/null || true' EXIT

if pgrep -f "$root/.venv/bin/python3 .venv/bin/pytest" >/dev/null 2>&1; then
  echo "stop-pytest: skipped; pytest already running"
  exit 0
fi

if [[ -x .venv/bin/pytest ]]; then
  .venv/bin/pytest tests/test_workspace_ui_contract.py tests/test_liquid_glass_scope_contract.py -q --tb=short -x 2>&1 | tail -5
fi
