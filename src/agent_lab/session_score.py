"""Offline session quality KPIs (Phase H4)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent_lab.plan_refs import validate_plan_refs
from agent_lab.communicate_kpis import communicate_counts, communicate_scores
from agent_lab.room_objections import list_objections
from agent_lab.run_meta import read_run_meta

_TOKEN_RE = re.compile(r"[a-zA-Z0-9가-힣]{2,}")
_DUP_JACCARD_THRESHOLD = 0.65
_TERMINAL_EXEC_STATUSES = frozenset(
    {"rejected", "completed", "review_required", "merged", "merge_conflict"}
)
_WORKTREE_TERMINAL_STATUSES = frozenset({"merged", "rejected", "merge_conflict"})


def _load_chat_messages(folder: Path) -> list[dict[str, Any]]:
    chat_path = folder / "chat.jsonl"
    if not chat_path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in chat_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


def _word_set(text: str) -> set[str]:
    return {w.lower() for w in _TOKEN_RE.findall(text or "")}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _first_speech_line(content: str) -> str:
    for raw in (content or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("```"):
            continue
        return line
    return ""


def _action_key(row: dict[str, Any]) -> str:
    idx = row.get("action_index")
    aid = row.get("action_id")
    if idx is not None:
        return f"idx:{idx}"
    if aid:
        return f"id:{aid}"
    return f"exec:{row.get('id', '?')}"


def _objection_resolution_rate(run_meta: dict[str, Any]) -> tuple[float | None, dict[str, int]]:
    rows = list_objections(run_meta)
    total = len(rows)
    if total == 0:
        return None, {"total": 0, "resolved": 0, "open": 0}
    resolved = sum(
        1
        for o in rows
        if o.get("status") in ("resolved_accepted", "resolved_wontfix")
    )
    open_n = sum(1 for o in rows if o.get("status") == "open")
    return resolved / total, {"total": total, "resolved": resolved, "open": open_n}


def _execute_first_try_rate(
    run_meta: dict[str, Any],
) -> tuple[float | None, dict[str, int]]:
    executions = [
        e for e in (run_meta.get("executions") or []) if isinstance(e, dict)
    ]
    prior_rejected: dict[str, bool] = {}
    first_try = 0
    retried = 0
    terminal = 0
    for row in executions:
        key = _action_key(row)
        status = str(row.get("status") or "")
        if status not in _TERMINAL_EXEC_STATUSES:
            continue
        terminal += 1
        if prior_rejected.get(key):
            retried += 1
        else:
            first_try += 1
        if status == "rejected":
            prior_rejected[key] = True
    if terminal == 0:
        return None, {"terminal": 0, "first_try": 0, "retried": 0}
    return first_try / terminal, {
        "terminal": terminal,
        "first_try": first_try,
        "retried": retried,
    }


def _execute_retry_rate(exec_counts: dict[str, int]) -> float | None:
    terminal = int(exec_counts.get("terminal") or 0)
    if terminal == 0:
        return None
    return int(exec_counts.get("retried") or 0) / terminal


def _execute_merge_kpis(
    run_meta: dict[str, Any],
) -> tuple[dict[str, float | None], dict[str, int]]:
    executions = [
        e for e in (run_meta.get("executions") or []) if isinstance(e, dict)
    ]
    total = len(executions)
    gitish = [
        e
        for e in executions
        if e.get("git_root")
        or e.get("isolation_effective") in {"worktree", "snapshot_override", "block"}
    ]
    worktree = [e for e in executions if e.get("isolation_effective") == "worktree"]
    snapshot_override = [
        e for e in executions if e.get("isolation_effective") == "snapshot_override"
    ]
    conflicts = [
        e
        for e in worktree
        if e.get("status") == "merge_conflict"
        or (
            isinstance(e.get("merge"), dict)
            and e["merge"].get("status") == "conflict"
        )
    ]

    prior_failed: dict[str, bool] = {}
    first_success = 0
    worktree_terminal = 0
    for row in worktree:
        status = str(row.get("status") or "")
        if status not in _WORKTREE_TERMINAL_STATUSES:
            continue
        worktree_terminal += 1
        key = _action_key(row)
        if status == "merged" and not prior_failed.get(key):
            first_success += 1
        if status in {"rejected", "merge_conflict"}:
            prior_failed[key] = True

    scores = {
        "worktree_usage_rate": (
            len(worktree) / len(gitish) if gitish else None
        ),
        "snapshot_override_rate": (
            len(snapshot_override) / total if total else None
        ),
        "merge_first_success_rate": (
            first_success / worktree_terminal if worktree_terminal else None
        ),
        "merge_conflict_rate": (
            len(conflicts) / len(worktree) if worktree else None
        ),
    }
    counts = {
        "total": total,
        "gitish": len(gitish),
        "worktree": len(worktree),
        "snapshot_override": len(snapshot_override),
        "worktree_terminal": worktree_terminal,
        "merge_first_success": first_success,
        "merge_conflict": len(conflicts),
    }
    return scores, counts


def _partial_turn_rate(run_meta: dict[str, Any]) -> tuple[float | None, dict[str, int]]:
    turns = [t for t in (run_meta.get("turns") or []) if isinstance(t, dict)]
    total = len(turns)
    if total == 0:
        return None, {"total": 0, "partial": 0, "failed": 0, "completed": 0}
    partial = sum(1 for t in turns if t.get("status") == "partial")
    failed = sum(1 for t in turns if t.get("status") == "failed")
    completed = sum(1 for t in turns if t.get("status") == "completed")
    return partial / total, {
        "total": total,
        "partial": partial,
        "failed": failed,
        "completed": completed,
    }


def _capability_cwd_kpis(
    run_meta: dict[str, Any],
) -> tuple[dict[str, float | None], dict[str, int]]:
    last_turn = run_meta.get("last_turn") or {}
    if not isinstance(last_turn, dict):
        last_turn = {}
    is_specialist = (
        run_meta.get("turn_profile") == "specialist"
        or last_turn.get("turn_profile") == "specialist"
    )
    if not is_specialist:
        return {
            "specialist_context_recorded": None,
            "asymmetric_capability_cwd": None,
            "capability_cwd_agent_count": None,
        }, {
            "specialist_contexts": 0,
            "recorded": 0,
            "agent_count": 0,
            "distinct_cwd": 0,
            "asymmetric": 0,
        }

    agents = ((last_turn.get("context") or {}).get("agents") or [])
    if not isinstance(agents, list):
        agents = []
    cwd_by_agent: dict[str, str] = {}
    for row in agents:
        if not isinstance(row, dict):
            continue
        agent = str(row.get("agent") or "").strip().lower()
        cwd = str(row.get("capability_cwd") or "").strip()
        if agent and cwd:
            cwd_by_agent[agent] = cwd

    agent_count = len(cwd_by_agent)
    distinct_cwd = len(set(cwd_by_agent.values()))
    recorded = agent_count > 0
    asymmetric = distinct_cwd >= 2
    return {
        "specialist_context_recorded": 1.0 if recorded else 0.0,
        "asymmetric_capability_cwd": 1.0 if asymmetric else 0.0,
        "capability_cwd_agent_count": float(agent_count),
    }, {
        "specialist_contexts": 1,
        "recorded": 1 if recorded else 0,
        "agent_count": agent_count,
        "distinct_cwd": distinct_cwd,
        "asymmetric": 1 if asymmetric else 0,
    }


def _ref_validity_rate(folder: Path) -> tuple[float | None, dict[str, int]]:
    result = validate_plan_refs(folder)
    total = len(result.refs)
    if total == 0:
        valid = 1.0 if result.valid else None
        return valid, {
            "plan_refs": 0,
            "invalid_refs": len(result.invalid_refs),
            "chat_lines": result.chat_line_count,
        }
    valid_n = total - len(result.invalid_refs)
    return valid_n / total, {
        "plan_refs": total,
        "invalid_refs": len(result.invalid_refs),
        "chat_lines": result.chat_line_count,
    }


def _duplicate_speech_rate(
    messages: list[dict[str, Any]],
) -> tuple[float | None, dict[str, int]]:
    last_user = -1
    for i, m in enumerate(messages):
        if m.get("role") == "user":
            last_user = i
    turn = messages[last_user + 1 :] if last_user >= 0 else messages
    agents = [
        m
        for m in turn
        if m.get("role") == "agent" and str(m.get("agent") or "").strip()
    ]
    if len(agents) < 2:
        return None, {"pairs": 0, "near_duplicates": 0, "agents": len(agents)}
    lines = [_first_speech_line(str(m.get("content") or "")) for m in agents]
    pairs = 0
    near = 0
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            if not lines[i] or not lines[j]:
                continue
            pairs += 1
            a, b = _word_set(lines[i]), _word_set(lines[j])
            if _jaccard(a, b) >= _DUP_JACCARD_THRESHOLD:
                near += 1
                continue
            li, lj = lines[i].lower(), lines[j].lower()
            if len(li) >= 24 and len(lj) >= 24 and (li.startswith(lj[:24]) or lj.startswith(li[:24])):
                near += 1
    rate = (near / pairs) if pairs else None
    return rate, {"pairs": pairs, "near_duplicates": near, "agents": len(agents)}


def score_session(folder: Path) -> dict[str, Any]:
    """Compute offline KPIs for a session folder."""
    folder = folder.expanduser().resolve()
    run_meta = read_run_meta(folder)
    messages = _load_chat_messages(folder)

    obj_rate, obj_counts = _objection_resolution_rate(run_meta)
    exec_rate, exec_counts = _execute_first_try_rate(run_meta)
    merge_scores, merge_counts = _execute_merge_kpis(run_meta)
    partial_rate, turn_counts = _partial_turn_rate(run_meta)
    capability_scores, capability_counts = _capability_cwd_kpis(run_meta)
    ref_rate, ref_counts = _ref_validity_rate(folder)
    dup_rate, dup_counts = _duplicate_speech_rate(messages)
    comm_counts = communicate_counts(run_meta)
    comm_scores = communicate_scores(comm_counts)

    scores: dict[str, float | None] = {
        "objection_resolution_rate": obj_rate,
        "execute_first_try_rate": exec_rate,
        "execute_retry_rate": _execute_retry_rate(exec_counts),
        "ref_validity_rate": ref_rate,
        "duplicate_speech_rate": dup_rate,
        "partial_turn_rate": partial_rate,
        **merge_scores,
        **capability_scores,
        **comm_scores,
    }
    summary_lines = _format_summary_lines(
        folder.name,
        scores,
        obj_counts,
        exec_counts,
        merge_counts,
        turn_counts,
        capability_counts,
        ref_counts,
        dup_counts,
    )
    return {
        "session_id": folder.name,
        "folder": str(folder),
        "scores": scores,
        "counts": {
            "objections": obj_counts,
            "executions": exec_counts,
            "execute_merge": merge_counts,
            "turns": turn_counts,
            "capability_cwd": capability_counts,
            "plan_refs": ref_counts,
            "duplicate_speech": dup_counts,
            "communicate": comm_counts,
        },
        "summary_lines": summary_lines,
    }


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.0f}%"


def _format_summary_lines(
    session_id: str,
    scores: dict[str, float | None],
    obj_counts: dict[str, int],
    exec_counts: dict[str, int],
    merge_counts: dict[str, int],
    turn_counts: dict[str, int],
    capability_counts: dict[str, int],
    ref_counts: dict[str, int],
    dup_counts: dict[str, int],
) -> list[str]:
    lines = [f"Session: {session_id}"]
    lines.append(
        f"  objection resolution: {_pct(scores['objection_resolution_rate'])} "
        f"({obj_counts.get('resolved', 0)}/{obj_counts.get('total', 0)} resolved)"
    )
    lines.append(
        f"  execute first-try: {_pct(scores['execute_first_try_rate'])} "
        f"({exec_counts.get('first_try', 0)}/{exec_counts.get('terminal', 0)} terminal)"
    )
    lines.append(
        f"  execute retry: {_pct(scores.get('execute_retry_rate'))} "
        f"({exec_counts.get('retried', 0)}/{exec_counts.get('terminal', 0)} terminal)"
    )
    lines.append(
        f"  worktree usage: {_pct(scores['worktree_usage_rate'])} "
        f"({merge_counts.get('worktree', 0)}/{merge_counts.get('gitish', 0)} git-ish)"
    )
    lines.append(
        f"  snapshot override: {_pct(scores['snapshot_override_rate'])} "
        f"({merge_counts.get('snapshot_override', 0)}/{merge_counts.get('total', 0)} executions)"
    )
    lines.append(
        f"  merge first-success: {_pct(scores['merge_first_success_rate'])} "
        f"({merge_counts.get('merge_first_success', 0)}/"
        f"{merge_counts.get('worktree_terminal', 0)} worktree terminal)"
    )
    lines.append(
        f"  merge conflict: {_pct(scores['merge_conflict_rate'])} "
        f"({merge_counts.get('merge_conflict', 0)}/{merge_counts.get('worktree', 0)} worktree)"
    )
    lines.append(
        f"  partial turns: {_pct(scores['partial_turn_rate'])} "
        f"({turn_counts.get('partial', 0)}/{turn_counts.get('total', 0)} turns)"
    )
    if scores["asymmetric_capability_cwd"] is None:
        lines.append("  specialist context cwd: n/a (no specialist context)")
    else:
        lines.append(
            f"  specialist context cwd: {_pct(scores['asymmetric_capability_cwd'])} asymmetric "
            f"({capability_counts.get('distinct_cwd', 0)} distinct cwd / "
            f"{capability_counts.get('agent_count', 0)} agents)"
        )
    lines.append(
        f"  plan ref validity: {_pct(scores['ref_validity_rate'])} "
        f"({ref_counts.get('plan_refs', 0)} refs, {ref_counts.get('invalid_refs', 0)} invalid)"
    )
    lines.append(
        f"  duplicate speech: {_pct(scores['duplicate_speech_rate'])} "
        f"({dup_counts.get('near_duplicates', 0)}/{dup_counts.get('pairs', 0)} near-dup pairs)"
    )
    return lines
