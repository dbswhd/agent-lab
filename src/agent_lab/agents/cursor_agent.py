import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from agent_lab.agent_models import DEFAULT_CURSOR_MODEL
from agent_lab.agent_permissions import normalize_agent_permissions, permission_preamble
from agent_lab.cursor_bridge import (
    cursor_sdk_client,
    format_cursor_connect_error,
    invalidate_workspace,
    is_transient_bridge_error,
)

_CURSOR_BRIDGE_ATTEMPTS = 3
_CURSOR_BRIDGE_RETRY_BACKOFF_S = 0.4


def _sdk_installed() -> bool:
    try:
        import cursor_sdk  # noqa: F401

        return True
    except ImportError:
        return False


def is_available() -> bool:
    from agent_lab.credential_store import provider_has_credentials

    return provider_has_credentials("cursor") and _sdk_installed()


def model_label() -> str:
    return os.getenv("CURSOR_MODEL", DEFAULT_CURSOR_MODEL)


def _resolve_cwd(permissions: dict[str, Any] | None) -> str:
    from agent_lab.workspace_roots import discuss_primary_workspace

    return str(discuss_primary_workspace(permissions))


def _wait_cursor_run(run: Any) -> None:
    """Block on SDK run.wait() but honour global cooperative cancel."""
    from agent_lab.run_control import RoomRunCancelled, is_cancelled

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(run.wait)
        while not fut.done():
            if is_cancelled():
                try:
                    run.cancel()
                except Exception:
                    pass
                try:
                    fut.result(timeout=90)
                except Exception:
                    pass
                raise RoomRunCancelled("run cancelled by user")
            time.sleep(0.2)
        fut.result()


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

    from agent_lab.run_control import (
        RoomRunCancelled,
        is_cancelled,
        register_cursor_run,
        unregister_cursor_run,
    )

    last_err: BaseException | None = None
    for attempt in range(_CURSOR_BRIDGE_ATTEMPTS):
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
                        register_cursor_run(run)
                        try:
                            _wait_cursor_run(run)
                            if is_cancelled():
                                raise RoomRunCancelled("run cancelled by user")
                            last_text = run.text().strip()
                        finally:
                            unregister_cursor_run(run)
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
            if (
                is_transient_bridge_error(e)
                and attempt < _CURSOR_BRIDGE_ATTEMPTS - 1
            ):
                invalidate_workspace(cwd_str)
                time.sleep(_CURSOR_BRIDGE_RETRY_BACKOFF_S * (attempt + 1))
                continue
            raise RuntimeError(format_cursor_connect_error(e)) from e
        except Exception as e:
            last_err = e
            if (
                is_transient_bridge_error(e)
                and attempt < _CURSOR_BRIDGE_ATTEMPTS - 1
            ):
                invalidate_workspace(cwd_str)
                time.sleep(_CURSOR_BRIDGE_RETRY_BACKOFF_S * (attempt + 1))
                continue
            raise RuntimeError(format_cursor_connect_error(e)) from e

    raise RuntimeError(format_cursor_connect_error(last_err or RuntimeError("Cursor bridge failed")))


def _build_agent_options(
    *,
    permissions: dict[str, Any] | None,
    cwd: str | Path | None,
    session_folder: str | Path | None,
    inbox_mcp: bool,
    api_key: str | None = None,
) -> tuple[str, Any]:
    from cursor_sdk import AgentOptions, LocalAgentOptions

    key = (api_key or os.getenv("CURSOR_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("CURSOR_API_KEY not set")

    perms = normalize_agent_permissions(permissions)
    cwd_str = str(cwd) if cwd is not None else _resolve_cwd(perms)
    mcp_servers = None
    if inbox_mcp and session_folder is not None:
        from agent_lab.cursor_inbox_mcp import (
            build_inbox_mcp_servers,
            mount_inbox_mcp_when_requested,
        )

        if mount_inbox_mcp_when_requested(inbox_mcp):
            mcp_servers = build_inbox_mcp_servers(Path(session_folder))

    agent_opts = AgentOptions(
        api_key=key,
        model=os.getenv("CURSOR_MODEL", DEFAULT_CURSOR_MODEL),
        local=LocalAgentOptions(cwd=cwd_str),
        mcp_servers=mcp_servers,
    )
    return cwd_str, agent_opts


def _build_send_options(
    on_activity: Any | None,
    on_bridge_event: Any | None = None,
) -> Any | None:
    if not on_activity and not on_bridge_event:
        return None
    from cursor_sdk import SendOptions

    from agent_lab.bridge_stdout_parser import parse_stream_update

    def _dispatch(update: Any, *, from_step: bool) -> None:
        for kind, data in parse_stream_update(update, from_step=from_step):
            if kind == "text":
                if on_bridge_event:
                    on_bridge_event("text", data)
                continue
            if kind in {"tool_start", "tool_output", "tool_done"}:
                if on_bridge_event:
                    on_bridge_event(kind, data)
                continue
            if kind == "activity":
                text = str(data.get("text") or "")
                if on_bridge_event:
                    on_bridge_event("activity", data)
                elif on_activity and text:
                    on_activity(text)

    return SendOptions(
        on_delta=lambda u: _dispatch(u, from_step=False),
        on_step=lambda s: _dispatch(s, from_step=True),
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
    on_bridge_event: Any | None = None,
    session_folder: str | Path | None = None,
    inbox_mcp: bool = False,
    gate_after: int | None = None,
    gate: Callable[[], bool] | None = None,
    extra_prompts_if_gate: list[str] | None = None,
    request_structured_envelope: bool = False,
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

    prepared = _prepare_prompts(system, prompts)
    if request_structured_envelope:
        from agent_lab.structured_envelope_adapter import structured_envelope_system_addon

        addon = structured_envelope_system_addon(compact=True)
        if prepared:
            prepared[0] = f"{prepared[0]}\n\n{addon}"
    from agent_lab.agent_hooks_materializer import native_cursor_hooks_overlay
    from agent_lab.credential_store import call_with_credential_fallback

    def _run(api_key: str | None) -> str:
        cwd_local, opts = _build_agent_options(
            permissions=permissions,
            cwd=cwd,
            session_folder=session_folder,
            inbox_mcp=inbox_mcp,
            api_key=api_key,
        )
        with native_cursor_hooks_overlay(session_folder, cwd_local):
            return _run_cursor_session(
                cwd_str=cwd_local,
                agent_opts=opts,
                prompts=prepared,
                send_opts=_build_send_options(on_activity, on_bridge_event),
                gate_after=gate_after,
                gate=gate,
                extra_prompts_if_gate=extra_prompts_if_gate,
            )

    return call_with_credential_fallback("cursor", _run)


def respond(
    system: str,
    user: str,
    *,
    permissions: dict[str, Any] | None = None,
    cwd: str | Path | None = None,
    on_activity: Any | None = None,
    on_bridge_event: Any | None = None,
    follow_ups: list[str] | None = None,
    session_folder: str | Path | None = None,
    inbox_mcp: bool = False,
    request_structured_envelope: bool = False,
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
        on_bridge_event=on_bridge_event,
        session_folder=session_folder,
        inbox_mcp=inbox_mcp,
        request_structured_envelope=request_structured_envelope,
    )
