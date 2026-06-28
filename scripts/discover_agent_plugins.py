#!/usr/bin/env python3
"""Phase A/B: list Claude/Codex plugins & MCP (read-only). See docs/PLUGIN-DISCOVERY.md."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_lab.plugin_discovery import discover_plugins  # noqa: E402
from agent_lab.workspace.roots import discuss_primary_workspace  # noqa: E402


def main() -> int:
    workspace = Path(discuss_primary_workspace({}) or ROOT)
    payload = discover_plugins(workspace)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
