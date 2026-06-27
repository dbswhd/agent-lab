"""Execute-lane engine adapters — Cursor / Codex transport (H5)."""

from __future__ import annotations

from typing import Any

from agent_lab.runtime.adapters.types import (
    DEFAULT_EXECUTE_AGENT,
    EXECUTE_AGENT_IDS,
    ExecuteAgentId,
    ExecuteInvokeRequest,
    RepairInvokeRequest,
)


def normalize_execute_agent(executor: str | None) -> ExecuteAgentId:
    agent_id = str(executor or DEFAULT_EXECUTE_AGENT).strip().lower()
    if agent_id not in EXECUTE_AGENT_IDS:
        raise ValueError("execute agent must be cursor or codex")
    return agent_id  # type: ignore[return-value]


def execute_agent_available(agent_id: str) -> bool:
    if agent_id == "cursor":
        from agent_lab.agents.cursor_agent import is_available

        return is_available()
    if agent_id == "codex":
        from agent_lab.agents.codex_agent import is_available

        return is_available()
    return False


def pick_repair_agent(
    target: dict[str, Any],
    requested: str | None,
) -> ExecuteAgentId:
    from agent_lab.agents.registry import available_agents

    allowed = EXECUTE_AGENT_IDS
    if requested and requested not in allowed:
        raise ValueError("repair executor must be cursor or codex")
    ready = set(available_agents())
    candidates = [
        requested,
        str(target.get("executor") or ""),
        "cursor",
        "codex",
    ]
    for candidate in candidates:
        if candidate in allowed and candidate in ready:
            return candidate  # type: ignore[return-value]
    raise RuntimeError("Cursor/Codex repair executor unavailable")


def invoke_execute(agent_id: ExecuteAgentId, req: ExecuteInvokeRequest) -> str:
    """Run execute-lane agent (dry-run / implement)."""
    if (
        req.inbox_mcp
        and req.session_folder is not None
        and req.plan_phase_user is not None
        and req.implement_phase_user is not None
        and req.inbox_gate is not None
    ):
        return _invoke_execute_inbox_session(agent_id, req)

    if agent_id == "cursor":
        from agent_lab.agents.cursor_agent import respond

        return respond(
            system=req.system,
            user=req.user,
            permissions=req.permissions,
            cwd=req.cwd,
            on_activity=req.on_activity,
            on_bridge_event=req.on_bridge_event,
            follow_ups=req.verify_follow_ups,
            session_folder=req.session_folder,
            inbox_mcp=req.inbox_mcp,
        )

    from agent_lab.agents.codex_agent import respond

    codex_permissions = dict(req.permissions)
    codex_permissions["_discuss_cwd"] = str(req.cwd.resolve())
    follow_up = _codex_verify_follow_up(req.verify_follow_ups)
    codex_user = f"{req.user}\n\n{follow_up}" if follow_up else req.user
    return respond(
        system=req.system,
        user=codex_user,
        permissions=codex_permissions,
        on_activity=req.on_activity,
        on_bridge_event=req.on_bridge_event,
        room_turn=False,
        session_folder=req.session_folder,
        inbox_mcp=req.inbox_mcp,
    )


def _invoke_execute_inbox_session(agent_id: ExecuteAgentId, req: ExecuteInvokeRequest) -> str:
    assert req.plan_phase_user is not None
    assert req.implement_phase_user is not None
    assert req.inbox_gate is not None
    extra = [req.implement_phase_user, *req.verify_follow_ups]

    if agent_id == "cursor":
        from agent_lab.agents.cursor_agent import respond_session

        return respond_session(
            req.system,
            [req.plan_phase_user],
            permissions=req.permissions,
            cwd=req.cwd,
            on_activity=req.on_activity,
            session_folder=req.session_folder,
            inbox_mcp=True,
            gate_after=0,
            gate=req.inbox_gate,
            extra_prompts_if_gate=extra,
        )

    from agent_lab.agents.codex_agent import respond_session

    codex_permissions = dict(req.permissions)
    codex_permissions["_discuss_cwd"] = str(req.cwd.resolve())
    return respond_session(
        req.system,
        [req.plan_phase_user],
        permissions=codex_permissions,
        on_activity=req.on_activity,
        room_turn=False,
        session_folder=req.session_folder,
        inbox_mcp=True,
        gate_after=0,
        gate=req.inbox_gate,
        extra_prompts_if_gate=extra,
    )


def verify_follow_up_text(verify: str) -> str:
    """Follow-up prompt appended after implement (execute lane)."""
    return f"""Phase 2 — verify and fix (same Cursor session, keep using tools):
- Verification criterion from plan: {verify}
- Re-read changed files; run tests/commands/build steps named in the criterion.
- If anything fails, fix and re-check before you finish.
- End with a line: VERIFICATION: PASS — … or VERIFICATION: FAIL — …
- Then 3–5 lines summarizing files touched and what you verified."""


def verify_follow_ups(verify: str) -> list[str]:
    text = (verify or "").strip()
    if not text or text in {"검증 기준 없음", "-", "—", "none", "N/A"}:
        return []
    return [verify_follow_up_text(text)]


def _codex_verify_follow_up(verify_follow_ups: list[str]) -> str:
    if not verify_follow_ups:
        return ""
    text = verify_follow_ups[0] if len(verify_follow_ups) == 1 else "\n".join(verify_follow_ups)
    return verify_follow_up_text(text).replace("same Cursor session", "same execution")


def invoke_repair(agent_id: ExecuteAgentId, req: RepairInvokeRequest) -> str:
    """Run L3 repair agent in worktree."""
    effective = dict(req.permissions)
    effective["_discuss_cwd"] = str(req.cwd.resolve())
    if agent_id == "cursor":
        from agent_lab.agents import cursor_agent

        return cursor_agent.respond(
            system=req.system,
            user=req.user,
            permissions=effective,
            cwd=req.cwd,
            follow_ups=req.verify_follow_ups,
        )
    from agent_lab.agents import codex_agent

    return codex_agent.respond(
        system=req.system,
        user=req.user,
        permissions=effective,
        room_turn=False,
    )
