#!/usr/bin/env bash
# teammate_idle hook — optional stdout becomes peer nudge; exit 2 blocks idle with stderr.
set -euo pipefail
payload="$(cat)"
# Default: no-op (built-in nudge applies when in_progress tasks exist).
exit 0
