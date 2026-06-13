#!/usr/bin/env bash
# Install macOS launchd agents for Trading Mission scheduler + watcher + delta queue.
set -euo pipefail

AGENT_LAB_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENT_LAB_HOME="${AGENT_LAB_HOME:-$HOME/.agent-lab}"
AGENT_LAB_VENV_PYTHON="${AGENT_LAB_VENV_PYTHON:-$AGENT_LAB_ROOT/.venv/bin/python}"
QUANT_PIPELINE_ROOT="${QUANT_PIPELINE_ROOT:-$HOME/Desktop/pipeline}"
AGENTIC_TRADING_DB="${AGENTIC_TRADING_DB:-$HOME/Projects/quant-agentic-trading/data/agentic_trading/control_plane.sqlite3}"
AGENTIC_QUANT_PIPELINE_SRC="${AGENTIC_QUANT_PIPELINE_SRC:-$HOME/Projects/quant-agentic-trading/src}"
AGENT_LAB_FRESHNESS_PYTHON="${AGENT_LAB_FRESHNESS_PYTHON:-$QUANT_PIPELINE_ROOT/.venv/bin/python}"
LAUNCH_AGENTS_DIR="${LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"

mkdir -p "$AGENT_LAB_HOME/logs" "$LAUNCH_AGENTS_DIR"

render_plist() {
  local src="$1"
  local dest="$2"
  sed \
    -e "s|__AGENT_LAB_ROOT__|$AGENT_LAB_ROOT|g" \
    -e "s|__AGENT_LAB_HOME__|$AGENT_LAB_HOME|g" \
    -e "s|__AGENT_LAB_VENV_PYTHON__|$AGENT_LAB_VENV_PYTHON|g" \
    -e "s|__QUANT_PIPELINE_ROOT__|$QUANT_PIPELINE_ROOT|g" \
    -e "s|__AGENTIC_TRADING_DB__|$AGENTIC_TRADING_DB|g" \
    -e "s|__AGENTIC_QUANT_PIPELINE_SRC__|$AGENTIC_QUANT_PIPELINE_SRC|g" \
    -e "s|__AGENT_LAB_FRESHNESS_PYTHON__|$AGENT_LAB_FRESHNESS_PYTHON|g" \
    "$src" > "$dest"
}

for name in com.agentlab.trading-premarket com.agentlab.trading-watcher com.agentlab.trading-delta; do
  src="$AGENT_LAB_ROOT/scripts/deploy/${name}.plist"
  dest="$LAUNCH_AGENTS_DIR/${name}.plist"
  render_plist "$src" "$dest"
  launchctl bootout "gui/$(id -u)/$name" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$dest"
  echo "loaded $dest"
done

echo "Mission triggers installed. Logs: $AGENT_LAB_HOME/logs/"
