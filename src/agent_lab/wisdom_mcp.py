from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

WISDOM_MCP_SERVER_NAME = "agent-lab-wisdom"


def wisdom_mcp_stdio_spec(session_folder: Path) -> dict[str, Any]:
    env = {
        **os.environ,
        "AGENT_LAB_SESSION_FOLDER": str(session_folder.resolve()),
    }
    enabled = os.getenv("AGENT_LAB_WISDOM_MCP")
    if enabled is not None:
        env["AGENT_LAB_WISDOM_MCP"] = enabled
    wisdom_path = os.getenv("AGENT_LAB_WISDOM_PATH")
    if wisdom_path is not None:
        env["AGENT_LAB_WISDOM_PATH"] = wisdom_path
    return {
        "command": sys.executable,
        "args": ["-m", "agent_lab.wisdom_mcp_server"],
        "env": env,
    }
