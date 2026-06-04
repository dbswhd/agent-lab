#!/usr/bin/env bash
# CC-hooks Stop: quick pytest tail on agent stop (dev-tool only).
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"
if [[ -x .venv/bin/pytest ]]; then
  .venv/bin/pytest tests/ -q --tb=short -x 2>&1 | tail -5
fi
