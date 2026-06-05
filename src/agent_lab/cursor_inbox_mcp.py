import os
import sys
from pathlib import Path
from typing import Any

from agent_lab.agent_models import DEFAULT_CURSOR_MODEL
from agent_lab.agent_permissions import normalize_agent_permissions, permission_preamble


def _execute_inbox_mcp_enabled() -> bool:
    raw = os.getenv("AGENT_LAB_EXECUTE_INBOX", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def build_inbox_mcp_servers(session_folder: Path) -> dict[str, Any]:
    from cursor_sdk.types import StdioMcpServerConfig

    env = {
        **os.environ,
        "AGENT_LAB_SESSION_FOLDER": str(session_folder.resolve()),
    }
    return {
        "agent-lab-inbox": StdioMcpServerConfig(
            command=sys.executable,
            args=["-m", "agent_lab.inbox_mcp_server"],
            env=env,
        )
    }
