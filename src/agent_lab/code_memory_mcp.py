from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

CODE_MEMORY_MCP_SERVER_NAME = "agent-lab-code-memory"


def code_memory_mcp_stdio_spec(session_folder: Path) -> dict[str, Any]:
    env = {
        **os.environ,
        "AGENT_LAB_SESSION_FOLDER": str(session_folder.resolve()),
    }
    enabled = os.getenv("AGENT_LAB_CODE_MEMORY_MCP")
    if enabled is not None:
        env["AGENT_LAB_CODE_MEMORY_MCP"] = enabled
    mode = os.getenv("AGENT_LAB_CODE_MEMORY_MODE")
    if mode is not None:
        env["AGENT_LAB_CODE_MEMORY_MODE"] = mode
    root = os.getenv("AGENT_LAB_CODE_MEMORY_ROOT")
    if root is not None:
        env["AGENT_LAB_CODE_MEMORY_ROOT"] = root
    return {
        "command": sys.executable,
        "args": ["-m", "agent_lab.code_memory_mcp_server"],
        "env": env,
    }
