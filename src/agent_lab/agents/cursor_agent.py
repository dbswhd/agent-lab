import os
from pathlib import Path
from typing import Any

from agent_lab.agent_models import DEFAULT_CURSOR_MODEL
from agent_lab.agent_permissions import normalize_agent_permissions, permission_preamble
from agent_lab.cursor_bridge import (
    cursor_sdk_client,
    format_cursor_connect_error,
    invalidate_workspace,
)


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
    from agent_lab.workspace_roots import discuss_primary_workspace

    return str(discuss_primary_workspace(permissions))


def _connection_refused(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "connection refused" in text or "errno 61" in text or "connecterror" in text


def _run_cursor_session(
    *,
    cwd_str: str,
    agent_opts: Any,
    prompts: list[str],
    send_opts: Any | None,
) -> str:
    from cursor_sdk import Agent, CursorAgentError

    last_err: BaseException | None = None
    for attempt in range(2):
        try:
            with cursor_sdk_client(cwd_str) as client:
                agent = Agent.create(agent_opts, client=client)
                try:
                    last_text = ""
                    for prompt in prompts:
                        run = agent.send(prompt, send_opts)
                        run.wait()
                        last_text = run.text().strip()
                    return last_text
                finally:
                    agent.close()
        except CursorAgentError as e:
            last_err = e
            if attempt == 0 and _connection_refused(e):
                invalidate_workspace(cwd_str)
                continue
            raise RuntimeError(format_cursor_connect_error(e)) from e
        except Exception as e:
            last_err = e
            if attempt == 0 and _connection_refused(e):
                invalidate_workspace(cwd_str)
                continue
            raise RuntimeError(format_cursor_connect_error(e)) from e

    raise RuntimeError(format_cursor_connect_error(last_err or RuntimeError("Cursor bridge failed")))


def respond(
    system: str,
    user: str,
    *,
    permissions: dict[str, Any] | None = None,
    cwd: str | Path | None = None,
    on_activity: Any | None = None,
    follow_ups: list[str] | None = None,
) -> str:
    from agent_lab.agents.prompts import CURSOR_ROOM

    api_key = os.getenv("CURSOR_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("CURSOR_API_KEY not set")

    try:
        from cursor_sdk import AgentOptions, LocalAgentOptions, SendOptions
    except ImportError as e:
        raise RuntimeError(
            "Install cursor-sdk: pip install cursor-sdk"
        ) from e

    from agent_lab.cursor_activity import (
        format_conversation_step,
        format_interaction_update,
    )

    perms = normalize_agent_permissions(permissions)
    extra = permission_preamble(perms, "cursor")
    system_block = system or CURSOR_ROOM
    if extra and "[고정 constraints]" not in user:
        system_block = f"{system_block}\n\n{extra}"
    prompt = f"{system_block}\n\n---\n\n{user}" if user.strip() else system_block

    cwd_str = str(cwd) if cwd is not None else _resolve_cwd(perms)
    agent_opts = AgentOptions(
        api_key=api_key,
        model=os.getenv("CURSOR_MODEL", DEFAULT_CURSOR_MODEL),
        local=LocalAgentOptions(cwd=cwd_str),
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

    prompts = [prompt]
    for follow in follow_ups or []:
        text = follow.strip()
        if text:
            prompts.append(text)

    return _run_cursor_session(
        cwd_str=cwd_str,
        agent_opts=agent_opts,
        prompts=prompts,
        send_opts=send_opts,
    )
