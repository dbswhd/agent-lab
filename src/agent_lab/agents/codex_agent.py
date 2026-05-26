from agent_lab import codex_cli
from agent_lab.agents.prompts import CODEX_ROOM


def is_available() -> bool:
    return codex_cli.is_available()


def respond(system: str, user: str, *, permissions: dict | None = None) -> str:
    return codex_cli.invoke(system or CODEX_ROOM, user, permissions=permissions)
