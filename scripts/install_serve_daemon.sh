#!/usr/bin/env bash
# Install macOS launchd agent for Agent Lab serve --daemon (Mission OS scheduler).
set -euo pipefail

AGENT_LAB_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENT_LAB_HOME="${AGENT_LAB_HOME:-$HOME/.agent-lab}"
AGENT_LAB_VENV_PYTHON="${AGENT_LAB_VENV_PYTHON:-$AGENT_LAB_ROOT/.venv/bin/python}"
LAUNCH_AGENTS_DIR="${LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"
NAME="com.agentlab.serve-daemon"

mkdir -p "$AGENT_LAB_HOME/logs" "$LAUNCH_AGENTS_DIR"

src="$AGENT_LAB_ROOT/scripts/deploy/${NAME}.plist"
dest="$LAUNCH_AGENTS_DIR/${NAME}.plist"

sed \
  -e "s|__AGENT_LAB_ROOT__|$AGENT_LAB_ROOT|g" \
  -e "s|__AGENT_LAB_HOME__|$AGENT_LAB_HOME|g" \
  -e "s|__AGENT_LAB_VENV_PYTHON__|$AGENT_LAB_VENV_PYTHON|g" \
  "$src" > "$dest"

launchctl bootout "gui/$(id -u)/$NAME" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$dest"
echo "loaded $dest"
echo "Health: curl -s http://127.0.0.1:8765/api/health/daemon | jq ."
echo "Logs: $AGENT_LAB_HOME/logs/serve-daemon.{out,err}"
