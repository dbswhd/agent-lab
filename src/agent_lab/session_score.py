"""Offline session quality KPIs (Phase H4)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent_lab.plan_refs import validate_plan_refs
from agent_lab.room_objections import list_objections
from agent_lab.run_meta import read_run_meta

_TOKEN_RE = re.compile(r"[a-zA-Z0-9가-힣]{2,}")
_DUP_JACCARD_THRESHOLD = 0.65
_TERMINAL_EXEC_STATUSES = frozenset({"rejected", "completed", "review_required"})


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
    ref_rate, ref_counts = _ref_validity_rate(folder)
    dup_rate, dup_counts = _duplicate_speech_rate(messages)

    scores: dict[str, float | None] = {
        "objection_resolution_rate": obj_rate,
        "execute_first_try_rate": exec_rate,
        "ref_validity_rate": ref_rate,
        "duplicate_speech_rate": dup_rate,
    }
    summary_lines = _format_summary_lines(
        folder.name,
        scores,
        obj_counts,
        exec_counts,
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
            "plan_refs": ref_counts,
            "duplicate_speech": dup_counts,
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
        f"  plan ref validity: {_pct(scores['ref_validity_rate'])} "
        f"({ref_counts.get('plan_refs', 0)} refs, {ref_counts.get('invalid_refs', 0)} invalid)"
    )
    lines.append(
        f"  duplicate speech: {_pct(scores['duplicate_speech_rate'])} "
        f"({dup_counts.get('near_duplicates', 0)}/{dup_counts.get('pairs', 0)} near-dup pairs)"
    )
    return lines
