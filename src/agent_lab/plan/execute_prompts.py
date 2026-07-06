"""Cursor execute/plan-phase prompt builders and execute-agent invocation for thin execute."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.run.state import RunStateLike

from agent_lab.plan.actions import PlanAction
from agent_lab.runtime.adapters import (
    invoke_execute,
    normalize_execute_agent as _normalize_execute_agent,
    verify_follow_ups,
)


def _inbox_mcp_instructions(action: PlanAction) -> str:
    action_key = f"{action.kind}:{action.index}"
    return f"""
Human Inbox MCP (agent-lab-inbox) — mandatory for direction and GO:
- Before ANY file edits: plan-first phase. Draft a short execution plan from the approved plan.md.
- If blocked on direction, call `ask_human` with question + at least 2 options (never ask in prose).
- When the execution plan is ready, call `propose_build` with summary + action_ref="{action_key}" and wait for Human GO.
- Only after `propose_build` returns decision=go may you edit files (implement phase).
- If decision is defer or reject, stop without editing files.
- During implement, if blocked again, use `ask_human` only.
"""


def _cursor_plan_phase_prompt(
    action: PlanAction,
    *,
    expected_paths: list[str] | None = None,
    verify: str | None = None,
) -> str:
    expected = ", ".join(expected_paths or action.expected_paths()) or action.where
    verify_line = verify if verify is not None else action.verify
    inbox_block = _inbox_mcp_instructions(action)
    return f"""Agent Lab execute — plan-first phase ONLY (no file edits yet).
{inbox_block}
Plan action (from approved plan.md):
- 무엇을: {action.what}
- 어디서: {expected}
- 검증: {verify_line}

Phase 0 — plan-first:
- Read the repo as needed; draft a short execution plan for this action.
- If blocked on direction, call `ask_human` with at least 2 options (never ask in prose).
- When ready, call `propose_build` with summary + action_ref and STOP — do not edit files until Human GO."""


def _cursor_implement_phase_prompt(
    action: PlanAction,
    *,
    expected_paths: list[str] | None = None,
    verify: str | None = None,
    revise_request: dict[str, Any] | None = None,
) -> str:
    expected = ", ".join(expected_paths or action.expected_paths()) or action.where
    verify_line = verify if verify is not None else action.verify
    prompt = f"""Agent Lab execute — implement phase (Human GO received).

Phase 1 — implement (tools expected):
- Change only what is needed for this action.
- Prefer paths listed in "어디서": {expected}
- Do not refactor unrelated code.
- Do not commit; leave changes in the working tree.
- Read before edit; use tools like the IDE agent.
- During implement, if blocked again, use `ask_human` only.

Plan action:
- 무엇을: {action.what}
- 어디서: {expected}
- 검증: {verify_line}

When phase 1 edits are done, stop and wait — a phase 2 verification message follows in this same session."""
    if revise_request:
        chunk_ref = str(revise_request.get("chunk_ref") or "전체 diff")
        comment = str(revise_request.get("comment") or "").strip()
        selected_diff = str(revise_request.get("selected_diff") or "").strip()
        prompt += f"""

Human inline revise request:
- 선택 범위: {chunk_ref}
- 요청: {comment}

Revise the selected part without undoing correct parts of the plan action."""
        if selected_diff:
            prompt += f"""

Previous selected diff:
```diff
{selected_diff}
```"""
    return prompt


def _cursor_execute_prompt(
    action: PlanAction,
    *,
    expected_paths: list[str] | None = None,
    verify: str | None = None,
    revise_request: dict[str, Any] | None = None,
    inbox_mcp: bool = False,
) -> str:
    if inbox_mcp:
        return _cursor_plan_phase_prompt(
            action,
            expected_paths=expected_paths,
            verify=verify,
        )
    expected = ", ".join(expected_paths or action.expected_paths()) or action.where
    verify_line = verify if verify is not None else action.verify
    prompt = f"""Agent Lab thin execute — implement exactly one plan action.

Phase 1 — implement (tools expected):
- Change only what is needed for this action.
- Prefer paths listed in "어디서": {expected}
- Do not refactor unrelated code.
- Do not commit; leave changes in the working tree.
- Read before edit; use tools like the IDE agent.

Plan action:
- 무엇을: {action.what}
- 어디서: {expected}
- 검증: {verify_line}

When phase 1 edits are done, stop and wait — a phase 2 verification message follows in this same session."""
    if revise_request:
        chunk_ref = str(revise_request.get("chunk_ref") or "전체 diff")
        comment = str(revise_request.get("comment") or "").strip()
        selected_diff = str(revise_request.get("selected_diff") or "").strip()
        prompt += f"""

Human inline revise request:
- 선택 범위: {chunk_ref}
- 요청: {comment}

Revise the selected part without undoing correct parts of the plan action."""
        if selected_diff:
            prompt += f"""

Previous selected diff:
```diff
{selected_diff}
```"""
    return prompt


def _extract_draft_summary(text: str) -> str:
    body = (text or "").strip()
    if not body:
        return ""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    return "\n".join(lines[:8])


def _call_execute_agent(
    agent_id: str,
    *,
    user: str,
    permissions: dict[str, Any],
    cwd: Path,
    on_activity: Any,
    verify: str,
    session_folder: Path | None = None,
    inbox_mcp: bool = False,
    action: Any | None = None,
    expected_paths: list[str] | None = None,
    revise_request: dict[str, Any] | None = None,
) -> str:
    from agent_lab.runtime.adapters import ExecuteInvokeRequest

    system = "You implement approved plan actions with minimal scope."
    verify_ups = verify_follow_ups(verify)
    if session_folder is not None:
        from agent_lab.runtime.context import enrich_execute_prompt
        from agent_lab.run.meta import read_run_meta
        from agent_lab.session.plugin_runtime import (
            enrich_execute_permissions,
            execute_plugin_prompt_addon,
        )

        permissions = enrich_execute_permissions(permissions, session_folder)
        user = execute_plugin_prompt_addon(user, session_folder, agent_id)
        user = enrich_execute_prompt(user, read_run_meta(session_folder))

    req = ExecuteInvokeRequest(
        system=system,
        user=user,
        permissions=permissions,
        cwd=cwd,
        verify_follow_ups=verify_ups,
        on_activity=on_activity,
        session_folder=session_folder,
        inbox_mcp=inbox_mcp,
    )
    if inbox_mcp and session_folder is not None and action is not None:
        from agent_lab.human_inbox import execute_inbox_build_go

        req.plan_phase_user = _cursor_plan_phase_prompt(
            action,
            expected_paths=expected_paths,
            verify=verify,
        )
        req.implement_phase_user = _cursor_implement_phase_prompt(
            action,
            expected_paths=expected_paths,
            verify=verify,
            revise_request=revise_request,
        )
        req.inbox_gate = lambda: execute_inbox_build_go(session_folder)

    bridge = None
    run_meta: RunStateLike | None = None
    started_at = 0.0
    status = "ok"
    if session_folder is not None:
        import time

        from agent_lab.sidecar_accounting import sidecar_bridge_handler

        bridge, run_meta = sidecar_bridge_handler(
            session_folder,
            agent_id,
            kind="execute",
        )
        req.on_bridge_event = bridge
        started_at = time.monotonic()
    try:
        return invoke_execute(_normalize_execute_agent(agent_id), req)
    except Exception:
        status = "error"
        raise
    finally:
        if session_folder is not None and bridge is not None and run_meta is not None:
            from agent_lab.sidecar_accounting import flush_sidecar_call

            flush_sidecar_call(
                session_folder,
                run_meta,
                kind="execute",
                agent_id=agent_id,
                started_at=started_at,
                status=status,
            )


def _selected_revision_diff(
    diff: str,
    *,
    chunk_ref: str | None,
    line_start: int | None,
    line_end: int | None,
    max_chars: int = 6000,
) -> str:
    lines = (diff or "").splitlines()
    selected: list[str] = []
    if line_start is not None:
        start = max(0, line_start - 1)
        end = max(start + 1, line_end or line_start)
        selected = lines[start:end]
    elif chunk_ref:
        for index, line in enumerate(lines):
            if line.strip() != chunk_ref.strip():
                continue
            selected.append(line)
            for following in lines[index + 1 :]:
                if following.startswith("@@") or following.startswith("diff --git "):
                    break
                selected.append(following)
            break
    else:
        selected = lines
    return "\n".join(selected)[:max_chars]
