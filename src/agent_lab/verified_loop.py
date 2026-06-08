"""LazyCodex-inspired verified loop: agent-proposed goal → Human approve → Oracle VERIFIED."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.run_meta import patch_run_meta, read_run_meta

MAX_VERIFICATION_ATTEMPTS = 3
MAX_ITERATIONS = 100
DEFAULT_COMPLETION_PROMISE = "DONE"

_ULW_PROPOSAL_RE = re.compile(
    r"<ulw_proposal>\s*(.*?)\s*</ulw_proposal>",
    re.I | re.S,
)
_PROMISE_RE = re.compile(r"<promise>\s*([^<\n]+?)\s*</promise>", re.I)
_VERIFIED_RE = re.compile(
    r"<promise>\s*VERIFIED\s*</promise>",
    re.I,
)
_FIELD_RE = re.compile(
    r"^(goal|completion_promise|criteria)\s*[:：]\s*(.+)$",
    re.I | re.M,
)

ORACLE_SYSTEM_PROMPT = (
    "You are the Oracle — an independent read-only verification subagent.\n"
    "You MUST NOT write, edit, delegate, or propose further work.\n"
    "Judge whether the session transcript demonstrates the loop goal is achieved "
    "against the completion criteria.\n\n"
    "If satisfied, reply with exactly:\n"
    "Agent: oracle\n"
    "<promise>VERIFIED</promise>\n"
    "<task_metadata>\n"
    "session_id: {session_id}\n"
    "</task_metadata>\n"
    "Followed by one concise reason.\n\n"
    "If not satisfied, reply with:\n"
    "FAIL: <one concise reason>\n"
    "Never emit VERIFIED unless the evidence supports it."
)


def normalize_verified_profile(profile: str | None) -> bool:
    from agent_lab.room_team_orchestration import normalize_turn_profile

    return normalize_turn_profile(profile) == "verified"


def verified_loop_public(run: dict[str, Any] | None) -> dict[str, Any]:
    loop = dict((run or {}).get("verified_loop") or {})
    return {
        "verified_loop": loop,
        "verified_loop_pending": loop.get("status") == "pending_approval",
    }


def init_verified_loop(session_folder: Path) -> dict[str, Any]:
    now = _now()

    def _init(run: dict[str, Any]) -> dict[str, Any]:
        loop = dict(run.get("verified_loop") or {})
        if loop.get("loop_goal"):
            if loop.get("status") not in {"done", "failed", "cancelled"}:
                loop["status"] = "running"
            run["verified_loop"] = loop
            return run
        if loop.get("status") in {
            "running",
            "done",
            "failed",
            "pending_approval",
            "cancelled",
        }:
            return run
        loop.update(
            {
                "status": "proposing",
                "iteration": 0,
                "max_iterations": MAX_ITERATIONS,
                "verification_attempts": 0,
                "max_verification_attempts": MAX_VERIFICATION_ATTEMPTS,
                "checks": list(loop.get("checks") or []),
                "started_at": loop.get("started_at") or now,
            }
        )
        run["verified_loop"] = loop
        return run

    updated = patch_run_meta(session_folder, _init)
    return dict(updated.get("verified_loop") or {})


def _parse_proposal_block(block: str) -> dict[str, str] | None:
    fields: dict[str, str] = {}
    for key, value in _FIELD_RE.findall(block.strip()):
        fields[key.strip().lower()] = value.strip()
    goal = fields.get("goal", "").strip()
    if not goal:
        return None
    return {
        "goal": goal,
        "completion_promise": (
            fields.get("completion_promise") or DEFAULT_COMPLETION_PROMISE
        ).strip()
        or DEFAULT_COMPLETION_PROMISE,
        "criteria": fields.get("criteria", "").strip() or goal,
    }


def harvest_all_proposals(messages: Iterable[Any]) -> list[dict[str, str]]:
    text = _messages_text(messages)
    rows: list[dict[str, str]] = []
    for match in _ULW_PROPOSAL_RE.finditer(text):
        parsed = _parse_proposal_block(match.group(1))
        if parsed:
            rows.append(parsed)
    return rows


def merge_proposals(proposals: list[dict[str, str]]) -> dict[str, str] | None:
    if not proposals:
        return None
    primary = proposals[0]
    criteria_parts: list[str] = []
    alternates: list[str] = []
    seen_criteria: set[str] = set()
    for idx, row in enumerate(proposals):
        crit = str(row.get("criteria") or "").strip()
        if crit and crit not in seen_criteria:
            seen_criteria.add(crit)
            criteria_parts.append(crit)
        if idx > 0:
            alt_goal = str(row.get("goal") or "").strip()
            if alt_goal and alt_goal != primary["goal"]:
                alternates.append(alt_goal)
    if len(criteria_parts) == 1:
        merged_criteria = criteria_parts[0]
    elif criteria_parts:
        merged_criteria = "\n".join(
            f"({i + 1}) {part}" for i, part in enumerate(criteria_parts)
        )
    else:
        merged_criteria = primary["goal"]
    merged: dict[str, str] = {
        "goal": primary["goal"],
        "completion_promise": primary["completion_promise"],
        "criteria": merged_criteria,
    }
    if alternates:
        merged["alternates"] = alternates
    if len(proposals) > 1:
        merged["merged_from"] = len(proposals)
    return merged


def harvest_proposal(messages: Iterable[Any]) -> dict[str, str] | None:
    return merge_proposals(harvest_all_proposals(messages))


def record_proposed_goal(
    session_folder: Path,
    proposal: dict[str, str],
    *,
    source: str = "agents",
) -> dict[str, Any]:
    now = _now()

    def _record(run: dict[str, Any]) -> dict[str, Any]:
        loop = dict(run.get("verified_loop") or {})
        if loop.get("loop_goal") or loop.get("status") in {
            "running",
            "done",
            "failed",
        }:
            return run
        stored = {
            k: v
            for k, v in proposal.items()
            if k in {"goal", "completion_promise", "criteria", "alternates", "merged_from"}
        }
        loop["proposed"] = {
            **stored,
            "proposed_at": now,
            "source": source,
        }
        loop["status"] = "pending_approval"
        run["verified_loop"] = loop
        run["session_goal"] = {
            "text": proposal["goal"],
            "set_at": now,
            "updated_at": now,
            "set_by": source,
        }
        return run

    updated = patch_run_meta(session_folder, _record)
    return dict(updated.get("verified_loop") or {})


def approve_verified_loop(
    session_folder: Path,
    *,
    goal: str | None = None,
    completion_promise: str | None = None,
    criteria: str | None = None,
) -> dict[str, Any]:
    run = read_run_meta(session_folder)
    loop = dict(run.get("verified_loop") or {})
    if loop.get("status") not in {"pending_approval", "proposing"}:
        raise ValueError("verified loop is not awaiting approval")
    proposed = dict(loop.get("proposed") or {})
    goal_text = (goal or proposed.get("goal") or "").strip()
    criteria_in = (criteria or "").strip()
    proposed_criteria = str(proposed.get("criteria") or "").strip()
    if not criteria_in or criteria_in == goal_text:
        criteria_resolved = proposed_criteria or goal_text
    else:
        criteria_resolved = criteria_in
    approved = {
        "text": goal_text,
        "completion_promise": (
            completion_promise
            or proposed.get("completion_promise")
            or DEFAULT_COMPLETION_PROMISE
        ).strip()
        or DEFAULT_COMPLETION_PROMISE,
        "criteria": criteria_resolved,
        "approved_at": _now(),
        "approved_by": "human",
    }
    if not approved["text"]:
        raise ValueError("loop goal text is required")
    if not approved["criteria"]:
        approved["criteria"] = approved["text"]
    now = approved["approved_at"]
    oracle_session_id = f"oracle_{session_folder.name}_{uuid.uuid4().hex[:8]}"

    def _approve(current: dict[str, Any]) -> dict[str, Any]:
        current_loop = dict(current.get("verified_loop") or {})
        current_loop["loop_goal"] = approved
        current_loop["status"] = "running"
        current_loop["iteration"] = 0
        current_loop["verification_attempts"] = 0
        current_loop["oracle_session_id"] = oracle_session_id
        current_loop.pop("circuit_breaker", None)
        current["verified_loop"] = current_loop
        current["session_goal"] = {
            "text": approved["text"],
            "set_at": now,
            "updated_at": now,
            "set_by": "agents+human",
        }
        current["goal_loop"] = {
            "enabled": True,
            "status": "open",
            "max_checks": MAX_VERIFICATION_ATTEMPTS,
            "checks": [],
        }
        return current

    updated = patch_run_meta(session_folder, _approve)
    loop_out = dict(updated.get("verified_loop") or {})
    return {
        "verified_loop": loop_out,
        "continue_prompt": _loop_work_prompt(loop_out),
    }


def reject_verified_loop(session_folder: Path, *, note: str = "") -> dict[str, Any]:
    def _reject(run: dict[str, Any]) -> dict[str, Any]:
        loop = dict(run.get("verified_loop") or {})
        loop["status"] = "cancelled"
        loop["cancelled_at"] = _now()
        if note.strip():
            loop["cancel_note"] = note.strip()
        run["verified_loop"] = loop
        return run

    updated = patch_run_meta(session_folder, _reject)
    return dict(updated.get("verified_loop") or {})


def detect_completion_promise(
    messages: Iterable[Any],
    expected: str,
    *,
    since_iso: str | None = None,
) -> bool:
    promise = (expected or DEFAULT_COMPLETION_PROMISE).strip().upper()
    if not promise:
        return False
    text = _messages_text(messages, since_iso=since_iso)
    for match in _PROMISE_RE.finditer(text):
        if match.group(1).strip().upper() == promise:
            return True
    return False


def is_oracle_verified(raw: str, *, oracle_session_id: str | None = None) -> bool:
    body = str(raw or "")
    if not _VERIFIED_RE.search(body):
        return False
    if oracle_session_id and f"session_id: {oracle_session_id}" in body:
        return True
    if oracle_session_id and oracle_session_id.startswith("oracle_"):
        # Accept VERIFIED block even if session_id line uses folder id only.
        folder_part = oracle_session_id.split("_", 2)[-1][:8]
        if folder_part and folder_part in body:
            return True
    # Structured VERIFIED without strict session match (oracle output only).
    return "Agent: oracle" in body or _VERIFIED_RE.search(body) is not None


def run_verified_oracle(
    session_folder: Path,
    *,
    goal_text: str,
    criteria: str,
    completion_promise: str,
    messages_snapshot: Iterable[Any],
    oracle_call: Callable[[str], str] | None = None,
    since_iso: str | None = None,
) -> dict[str, Any]:
    run = read_run_meta(session_folder)
    loop = dict(run.get("verified_loop") or {})
    oracle_session_id = str(loop.get("oracle_session_id") or f"oracle_{session_folder.name}")
    transcript = _messages_text(messages_snapshot, since_iso=since_iso)
    prompt = (
        f"Loop goal:\n{goal_text}\n\n"
        f"Completion criteria:\n{criteria}\n\n"
        f"Expected completion promise from main session: {completion_promise}\n\n"
        f"Transcript:\n{transcript[-12000:] or '(empty)'}"
    )
    system = ORACLE_SYSTEM_PROMPT.format(session_id=oracle_session_id)
    if oracle_call is not None:
        raw = oracle_call(f"{system}\n\n{prompt}")
        source = "inject"
    else:
        from agent_lab import claude_cli

        raw = claude_cli.invoke(system, prompt, scribe=True, room_turn=False)
        source = "live"

    detail = str(raw or "").strip()
    verified = is_oracle_verified(detail, oracle_session_id=oracle_session_id)
    verdict = "verified" if verified else "fail"
    return {
        "at": _now(),
        "verdict": verdict,
        "detail": detail[:800],
        "source": source,
        "oracle_session_id": oracle_session_id,
    }


def maybe_handle_verified_loop_after_turn(
    session_folder: Path,
    messages_snapshot: Iterable[Any],
    turn_profile: str | None,
    *,
    oracle_call: Callable[[str], str] | None = None,
    cancelled: bool = False,
) -> dict[str, Any] | None:
    if not normalize_verified_profile(turn_profile):
        return None

    init_verified_loop(session_folder)
    run = read_run_meta(session_folder)
    loop = dict(run.get("verified_loop") or {})
    status = str(loop.get("status") or "proposing")

    if cancelled:
        loop = dict(read_run_meta(session_folder).get("verified_loop") or loop)
        return {
            "handled": True,
            "verified_loop": loop,
            "verified_loop_pending": loop.get("status") == "pending_approval",
            "continue_prompt": None,
            "cancelled": True,
        }

    if loop.get("loop_goal") and status in {"proposing", "pending_approval"}:
        status = "running"

    if status == "proposing":
        if loop.get("proposed") and loop.get("status") == "pending_approval":
            return {
                "handled": True,
                "verified_loop": loop,
                "verified_loop_pending": True,
                "continue_prompt": None,
            }
        proposal = harvest_proposal(messages_snapshot)
        if not proposal:
            topic = (session_folder / "topic.txt").read_text(encoding="utf-8").strip()
            proposal = {
                "goal": topic or "Complete the Human topic",
                "completion_promise": DEFAULT_COMPLETION_PROMISE,
                "criteria": topic or "Human topic addressed with evidence in transcript",
            }
            source = "fallback"
        else:
            source = "agents"
        loop = record_proposed_goal(session_folder, proposal, source=source)
        return {
            "handled": True,
            "verified_loop": loop,
            "verified_loop_pending": True,
            "continue_prompt": None,
        }

    if status == "pending_approval":
        return {
            "handled": True,
            "verified_loop": loop,
            "verified_loop_pending": True,
            "continue_prompt": None,
        }

    if status not in {"running"}:
        return {
            "handled": True,
            "verified_loop": loop,
            "verified_loop_pending": False,
            "continue_prompt": None,
        }

    loop_goal = dict(loop.get("loop_goal") or {})
    goal_text = str(loop_goal.get("text") or "").strip()
    if not goal_text:
        return None

    iteration = int(loop.get("iteration") or 0) + 1
    max_iterations = int(loop.get("max_iterations") or MAX_ITERATIONS)
    completion_promise = str(
        loop_goal.get("completion_promise") or DEFAULT_COMPLETION_PROMISE
    )
    since_iso = str(loop_goal.get("approved_at") or "").strip() or None

    def _patch_iteration(current: dict[str, Any]) -> dict[str, Any]:
        current_loop = dict(current.get("verified_loop") or {})
        current_loop["iteration"] = iteration
        current["verified_loop"] = current_loop
        return current

    patch_run_meta(session_folder, _patch_iteration)

    if iteration > max_iterations:
        return _circuit_break(
            session_folder,
            reason=f"iteration cap ({max_iterations}) reached",
        )

    if not detect_completion_promise(
        messages_snapshot,
        completion_promise,
        since_iso=since_iso,
    ):
        return {
            "handled": True,
            "verified_loop": read_run_meta(session_folder).get("verified_loop") or {},
            "verified_loop_pending": False,
            "continue_prompt": _loop_work_prompt(
                read_run_meta(session_folder).get("verified_loop") or {}
            ),
        }

    check = run_verified_oracle(
        session_folder,
        goal_text=goal_text,
        criteria=str(loop_goal.get("criteria") or goal_text),
        completion_promise=completion_promise,
        messages_snapshot=messages_snapshot,
        oracle_call=oracle_call,
        since_iso=since_iso,
    )

    def _record_check(current: dict[str, Any]) -> dict[str, Any]:
        current_loop = dict(current.get("verified_loop") or {})
        checks = list(current_loop.get("checks") or [])
        checks.append(check)
        current_loop["checks"] = checks
        current_loop["last_check"] = check
        current_loop["last_completion_signal"] = completion_promise
        if check["verdict"] == "verified":
            current_loop["status"] = "done"
            current_loop["verified_at"] = check["at"]
            current_loop.pop("continue_prompt", None)
            goal_loop = dict(current.get("goal_loop") or {})
            goal_loop["status"] = "achieved"
            goal_loop["achieved_at"] = check["at"]
            goal_loop["enabled"] = True
            goal_loop["checks"] = list(goal_loop.get("checks") or []) + [
                {
                    "at": check["at"],
                    "verdict": "pass",
                    "detail": check["detail"][:500],
                    "source": check["source"],
                }
            ]
            current["goal_loop"] = goal_loop
        else:
            attempts = int(current_loop.get("verification_attempts") or 0) + 1
            current_loop["verification_attempts"] = attempts
            if attempts >= int(
                current_loop.get("max_verification_attempts") or MAX_VERIFICATION_ATTEMPTS
            ):
                current_loop["status"] = "failed"
                current_loop["circuit_breaker"] = True
                current_loop["circuit_reason"] = (
                    f"Oracle verification failed {attempts} times"
                )
            else:
                current_loop["continue_prompt"] = (
                    "Oracle verification failed. Address the gaps and try again:\n"
                    f"{check['detail'][:400]}"
                )
        current["verified_loop"] = current_loop
        return current

    updated = patch_run_meta(session_folder, _record_check)
    loop_out = dict(updated.get("verified_loop") or {})
    result: dict[str, Any] = {
        "handled": True,
        "verified_loop": loop_out,
        "verified_loop_pending": False,
        "check": check,
        "continue_prompt": None,
    }
    if loop_out.get("status") == "running":
        result["continue_prompt"] = loop_out.get("continue_prompt") or _loop_work_prompt(
            loop_out
        )
    if loop_out.get("circuit_breaker"):
        result["circuit_breaker"] = True
    return result


def _circuit_break(session_folder: Path, *, reason: str) -> dict[str, Any]:
    def _break(run: dict[str, Any]) -> dict[str, Any]:
        loop = dict(run.get("verified_loop") or {})
        loop["status"] = "failed"
        loop["circuit_breaker"] = True
        loop["circuit_reason"] = reason
        run["verified_loop"] = loop
        return run

    updated = patch_run_meta(session_folder, _break)
    loop = dict(updated.get("verified_loop") or {})
    return {
        "handled": True,
        "verified_loop": loop,
        "verified_loop_pending": False,
        "continue_prompt": None,
        "circuit_breaker": True,
    }


def _loop_work_prompt(loop: dict[str, Any]) -> str:
    approved = dict(loop.get("loop_goal") or {})
    proposed = dict(loop.get("proposed") or {})
    source = approved if approved.get("text") else proposed
    text = str(source.get("text") or source.get("goal") or "").strip()
    promise = str(source.get("completion_promise") or DEFAULT_COMPLETION_PROMISE)
    criteria = str(source.get("criteria") or "").strip()
    if not criteria or criteria == text:
        criteria = str(proposed.get("criteria") or text).strip()
    lines = [
        "[Verified loop · work]",
        f"Goal: {text}",
        f"Criteria:\n{criteria}",
        f"When complete, emit exactly: <promise>{promise}</promise>",
        "Do NOT emit VERIFIED — only the Oracle may verify.",
    ]
    return "\n".join(lines)


VERIFIED_LOOP_GUIDANCE = """
[Verified loop mode · LazyCodex-style]
1) First round: ONE teammate emits the canonical <ulw_proposal> block; others ENDORSE/AMEND in plain text (no duplicate blocks).
<ulw_proposal>
goal: ...
completion_promise: DONE
criteria: ...
</ulw_proposal>
2) After Human approval, execute toward the goal and criteria above.
3) When done, emit: <promise>DONE</promise> (or the agreed completion_promise).
4) NEVER emit <promise>VERIFIED</promise> — only the Oracle subagent verifies.
""".strip()


def _parse_iso_ts(raw: str | None) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _message_ts(message: Any) -> datetime | None:
    if isinstance(message, dict):
        raw = message.get("ts") or message.get("timestamp")
    else:
        raw = getattr(message, "ts", None) or getattr(message, "timestamp", None)
    if raw is None:
        return None
    return _parse_iso_ts(str(raw))


def _message_after_cutoff(message: Any, cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True
    ts = _message_ts(message)
    if ts is None:
        return True
    if ts.tzinfo is None and cutoff.tzinfo is not None:
        ts = ts.replace(tzinfo=timezone.utc)
    if cutoff.tzinfo is None and ts.tzinfo is not None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    return ts >= cutoff


def _messages_text(
    messages: Iterable[Any],
    *,
    since_iso: str | None = None,
) -> str:
    cutoff = _parse_iso_ts(since_iso)
    rows: list[str] = []
    for message in messages:
        if not _message_after_cutoff(message, cutoff):
            continue
        if isinstance(message, dict):
            if str(message.get("role") or "").strip().lower() == "user":
                continue
            content = message.get("content") or message.get("body") or ""
        else:
            if str(getattr(message, "role", "") or "").strip().lower() == "user":
                continue
            content = getattr(message, "content", "")
        text = str(content or "").strip()
        if text:
            rows.append(text)
    return "\n".join(rows)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
