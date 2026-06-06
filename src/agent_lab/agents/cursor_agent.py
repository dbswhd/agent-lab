import os
from collections.abc import Callable
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
    gate_after: int | None = None,
    gate: Callable[[], bool] | None = None,
    extra_prompts_if_gate: list[str] | None = None,
) -> str:
    from cursor_sdk import Agent, CursorAgentError

    last_err: BaseException | None = None
    for attempt in range(2):
        try:
            with cursor_sdk_client(cwd_str) as client:
                agent = Agent.create(agent_opts, client=client)
                try:
                    last_text = ""
                    queue = list(prompts)
                    index = 0
                    while index < len(queue):
                        prompt = queue[index]
                        run = agent.send(prompt, send_opts)
                        run.wait()
                        last_text = run.text().strip()
                        if (
                            gate_after is not None
                            and index == gate_after
                            and gate is not None
                            and extra_prompts_if_gate
                        ):
                            if gate():
                                queue.extend(extra_prompts_if_gate)
                            else:
                                break
                        index += 1
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


def _build_agent_options(
    *,
    permissions: dict[str, Any] | None,
    cwd: str | Path | None,
    session_folder: str | Path | None,
    inbox_mcp: bool,
) -> tuple[str, Any]:
    from cursor_sdk import AgentOptions, LocalAgentOptions

    api_key = os.getenv("CURSOR_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("CURSOR_API_KEY not set")

    perms = normalize_agent_permissions(permissions)
    cwd_str = str(cwd) if cwd is not None else _resolve_cwd(perms)
    mcp_servers = None
    if inbox_mcp and session_folder is not None:
        from agent_lab.cursor_inbox_mcp import (
            build_inbox_mcp_servers,
            execute_inbox_mcp_enabled,
        )

        if execute_inbox_mcp_enabled():
            mcp_servers = build_inbox_mcp_servers(Path(session_folder))

    agent_opts = AgentOptions(
        api_key=api_key,
        model=os.getenv("CURSOR_MODEL", DEFAULT_CURSOR_MODEL),
        local=LocalAgentOptions(cwd=cwd_str),
        mcp_servers=mcp_servers,
    )
    return cwd_str, agent_opts


def _build_send_options(on_activity: Any | None) -> Any | None:
    if not on_activity:
        return None
    from cursor_sdk import SendOptions

    from agent_lab.cursor_activity import (
        format_conversation_step,
        format_interaction_update,
    )

    def _emit(label: str | None) -> None:
        if label and on_activity:
            on_activity(label)

    return SendOptions(
        on_delta=lambda u: _emit(format_interaction_update(u)),
        on_step=lambda s: _emit(format_conversation_step(s)),
    )


def _prepare_prompts(system: str, prompts: list[str], *, user: str | None = None) -> list[str]:
    from agent_lab.agents.prompts import CURSOR_ROOM

    system_block = system or CURSOR_ROOM
    bodies = [p.strip() for p in prompts if p and p.strip()]
    if user is not None and user.strip():
        bodies = [user.strip(), *bodies[1:]] if bodies else [user.strip()]
    if not bodies:
        return [system_block]
    first = bodies[0]
    prepared = [f"{system_block}\n\n---\n\n{first}" if first else system_block]
    prepared.extend(bodies[1:])
    return prepared


def respond_session(
    system: str,
    prompts: list[str],
    *,
    permissions: dict[str, Any] | None = None,
    cwd: str | Path | None = None,
    on_activity: Any | None = None,
    session_folder: str | Path | None = None,
    inbox_mcp: bool = False,
    gate_after: int | None = None,
    gate: Callable[[], bool] | None = None,
    extra_prompts_if_gate: list[str] | None = None,
) -> str:
    """Persistent Cursor session — RFC §4.6 E1.

    ``gate_after`` + ``gate`` + ``extra_prompts_if_gate`` implement plan-first →
    implement split: after prompt index ``gate_after``, append extra prompts only
    when ``gate()`` is true (e.g. MCP ``propose_build`` GO).
    """
    try:
        from cursor_sdk import AgentOptions  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "Install cursor-sdk: pip install cursor-sdk"
        ) from e

    cwd_str, agent_opts = _build_agent_options(
        permissions=permissions,
        cwd=cwd,
        session_folder=session_folder,
        inbox_mcp=inbox_mcp,
    )
    prepared = _prepare_prompts(system, prompts)
    return _run_cursor_session(
        cwd_str=cwd_str,
        agent_opts=agent_opts,
        prompts=prepared,
        send_opts=_build_send_options(on_activity),
        gate_after=gate_after,
        gate=gate,
        extra_prompts_if_gate=extra_prompts_if_gate,
    )


def respond(
    system: str,
    user: str,
    *,
    permissions: dict[str, Any] | None = None,
    cwd: str | Path | None = None,
    on_activity: Any | None = None,
    follow_ups: list[str] | None = None,
    session_folder: str | Path | None = None,
    inbox_mcp: bool = False,
) -> str:
    from agent_lab.agents.prompts import CURSOR_ROOM

    perms = normalize_agent_permissions(permissions)
    extra = permission_preamble(perms, "cursor")
    system_block = system or CURSOR_ROOM
    if extra and "[고정 constraints]" not in user:
        system_block = f"{system_block}\n\n{extra}"

    prompts = [user]
    for follow in follow_ups or []:
        text = follow.strip()
        if text:
            prompts.append(text)

    return respond_session(
        system_block,
        prompts,
        permissions=permissions,
        cwd=cwd,
        on_activity=on_activity,
        session_folder=session_folder,
        inbox_mcp=inbox_mcp,
    )
