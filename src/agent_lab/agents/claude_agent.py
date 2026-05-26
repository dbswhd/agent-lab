from typing import Any

from agent_lab import claude_cli
from agent_lab.agent_permissions import permission_preamble
from agent_lab.agents.prompts import CLAUDE_API_HANDOFF, CLAUDE_ROOM


def is_available() -> bool:
    return claude_cli.is_available()


def respond(
    system: str,
    user: str,
    *,
    permissions: dict[str, Any] | None = None,
) -> str:
    parts = [system or CLAUDE_ROOM, CLAUDE_API_HANDOFF]
    extra = permission_preamble(permissions, "claude")
    if extra:
        parts.append(extra)
    system_block = "\n\n".join(parts)
    return claude_cli.invoke(system_block, user, permissions=permissions)
