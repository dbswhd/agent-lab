import os
from pathlib import Path
from typing import Any

from agent_lab.agent_models import DEFAULT_CURSOR_MODEL
from agent_lab.agent_permissions import permission_preamble


def _sdk_installed() -> bool:
    try:
        import cursor_sdk  # noqa: F401

        return True
    except ImportError:
        return False


def is_available() -> bool:
    return bool(os.getenv("CURSOR_API_KEY", "").strip()) and _sdk_installed()


def model_label() -> str:
    return os.getenv("CURSOR_MODEL", DEFAULT_CURSOR_MODEL)


def _resolve_cwd(permissions: dict[str, Any] | None) -> str:
    from agent_lab.workspace_roots import primary_workspace

    return str(primary_workspace(permissions))


def respond(
    system: str,
    user: str,
    *,
    permissions: dict[str, Any] | None = None,
    on_activity: Any | None = None,
) -> str:
    from agent_lab.agents.prompts import CURSOR_ROOM

    api_key = os.getenv("CURSOR_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("CURSOR_API_KEY not set")

    try:
        from cursor_sdk import Agent, AgentOptions, LocalAgentOptions, SendOptions
    except ImportError as e:
        raise RuntimeError(
            "Install cursor-sdk: pip install cursor-sdk"
        ) from e

    from agent_lab.cursor_activity import (
        format_conversation_step,
        format_interaction_update,
    )

    extra = permission_preamble(permissions, "cursor")
    system_block = system or CURSOR_ROOM
    # Permissions and workspace roots live in user payload [고정 constraints].
    if extra and "[고정 constraints]" not in user:
        system_block = f"{system_block}\n\n{extra}"
    prompt = f"{system_block}\n\n---\n\n{user}" if user.strip() else system_block

    cwd = _resolve_cwd(permissions)
    agent_opts = AgentOptions(
        api_key=api_key,
        model=os.getenv("CURSOR_MODEL", DEFAULT_CURSOR_MODEL),
        local=LocalAgentOptions(cwd=cwd),
    )

    def _emit(label: str | None) -> None:
        if label and on_activity:
            on_activity(label)

    send_opts = None
    if on_activity:
        send_opts = SendOptions(
            on_delta=lambda u: _emit(format_interaction_update(u)),
            on_step=lambda s: _emit(format_conversation_step(s)),
        )

    agent = Agent.create(agent_opts)
    try:
        run = agent.send(prompt, send_opts)
        run.wait()
        return run.text().strip()
    finally:
        agent.close()
