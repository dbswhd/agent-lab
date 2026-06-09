"""External runner handoff JSON — GJC + H7 (MB-8)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.run_meta import patch_run_meta, read_run_meta

_PENDING_EXECUTION_STATUSES = frozenset(
    {"pending_approval", "pending", "review_required", "merge_conflict"}
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


REQUIRED_HANDOFF_KEYS: tuple[str, ...] = (
    "stopped_cleanly",
    "changed_files",
    "checks",
    "evidence_summary",
    "risks",
)


def validate_external_handoff(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    for key in REQUIRED_HANDOFF_KEYS:
        if key not in payload:
            errors.append(f"missing:{key}")
    if "stopped_cleanly" in payload and not isinstance(payload.get("stopped_cleanly"), bool):
        errors.append("stopped_cleanly must be boolean")
    if "changed_files" in payload and not isinstance(payload.get("changed_files"), list):
        errors.append("changed_files must be a list")
    if "checks" in payload:
        checks = payload.get("checks")
        if not isinstance(checks, list):
            errors.append("checks must be a list")
        else:
            for i, row in enumerate(checks):
                if not isinstance(row, dict):
                    errors.append(f"checks[{i}] must be object")
                    continue
                if "cmd" not in row and "command" not in row:
                    errors.append(f"checks[{i}] missing cmd")
                if "exit" not in row and "exit_code" not in row:
                    errors.append(f"checks[{i}] missing exit")
    if "risks" in payload and not isinstance(payload.get("risks"), list):
        errors.append("risks must be a list")
    if "evidence_summary" in payload and not str(payload.get("evidence_summary") or "").strip():
        errors.append("evidence_summary must be non-empty")
    return (not errors, errors)


def normalize_external_handoff(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for row in payload.get("checks") or []:
        if not isinstance(row, dict):
            continue
        checks.append(
            {
                "cmd": str(row.get("cmd") or row.get("command") or ""),
                "exit": int(row.get("exit") if row.get("exit") is not None else row.get("exit_code") or 0),
            }
        )
    return {
        "stopped_cleanly": bool(payload.get("stopped_cleanly")),
        "changed_files": [
            str(p) for p in (payload.get("changed_files") or []) if str(p).strip()
        ],
        "checks": checks,
        "evidence_summary": str(payload.get("evidence_summary") or "").strip(),
        "risks": [str(r) for r in (payload.get("risks") or []) if str(r).strip()],
        "attached_at": _now_iso(),
        "source": str(payload.get("source") or "api"),
        "tool_id": payload.get("tool_id"),
    }


def attach_external_handoff(
    folder: Path,
    *,
    execution_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    ok, errors = validate_external_handoff(payload)
    if not ok:
        raise ValueError("; ".join(errors))
    normalized = normalize_external_handoff(payload)

    def _attach(run: dict[str, Any]) -> dict[str, Any]:
        rows = list(run.get("executions") or [])
        for i, row in enumerate(rows):
            if not isinstance(row, dict) or row.get("id") != execution_id:
                continue
            updated = dict(row)
            updated["external_handoff"] = normalized
            rows[i] = updated
            run["executions"] = rows
            return run
        raise ValueError(f"execution not found: {execution_id}")

    patch_run_meta(folder, _attach)
    run = read_run_meta(folder)
    for row in run.get("executions") or []:
        if isinstance(row, dict) and row.get("id") == execution_id:
            return row
    raise ValueError(f"execution not found: {execution_id}")


def public_external_handoff(execution: dict[str, Any] | None) -> dict[str, Any] | None:
    if not execution:
        return None
    handoff = execution.get("external_handoff")
    return handoff if isinstance(handoff, dict) else None


def _looks_like_handoff(payload: dict[str, Any]) -> bool:
    ok, _ = validate_external_handoff(payload)
    return ok


def parse_handoff_payload(text: str) -> dict[str, Any] | None:
    """Extract handoff JSON from stdout/stderr or fenced block."""
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and _looks_like_handoff(parsed):
            return parsed
    except json.JSONDecodeError:
        pass
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.DOTALL)
    for block in reversed(fenced):
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and _looks_like_handoff(parsed):
            return parsed
    start = raw.rfind("{")
    while start >= 0:
        chunk = raw[start:]
        try:
            parsed = json.loads(chunk)
        except json.JSONDecodeError:
            start = raw.rfind("{", 0, start)
            continue
        if isinstance(parsed, dict) and _looks_like_handoff(parsed):
            return parsed
        start = raw.rfind("{", 0, start)
    return None


def pending_execution_for_handoff(run: dict[str, Any]) -> dict[str, Any] | None:
    for row in reversed(run.get("executions") or []):
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "") in _PENDING_EXECUTION_STATUSES:
            return row
    return None


def discover_handoff_payload(
    session_folder: Path,
    result: dict[str, Any],
) -> dict[str, Any] | None:
    for key in ("stdout", "stderr"):
        payload = parse_handoff_payload(str(result.get(key) or ""))
        if payload:
            return payload
    handoff_path = session_folder / "external_handoff.json"
    if handoff_path.is_file():
        try:
            parsed = json.loads(handoff_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, dict) and _looks_like_handoff(parsed):
            return parsed
    return None


def try_attach_handoff_from_external_result(
    session_folder: Path,
    result: dict[str, Any],
    *,
    tool_id: str | None = None,
) -> dict[str, Any] | None:
    """Auto-attach handoff JSON emitted by external runner stdout/file."""
    if not result.get("ok"):
        return None
    payload = discover_handoff_payload(session_folder, result)
    if not payload:
        return None
    run = read_run_meta(session_folder)
    pending = pending_execution_for_handoff(run)
    if not pending or not pending.get("id"):
        return {
            "attached": False,
            "reason": "no_pending_execution",
            "handoff_preview": payload.get("evidence_summary"),
        }
    payload = dict(payload)
    payload.setdefault("source", "external_runner")
    if tool_id:
        payload["tool_id"] = tool_id
    try:
        execution = attach_external_handoff(
            session_folder,
            execution_id=str(pending["id"]),
            payload=payload,
        )
    except ValueError as exc:
        return {
            "attached": False,
            "reason": str(exc),
            "execution_id": pending.get("id"),
        }
    return {
        "attached": True,
        "execution_id": pending.get("id"),
        "external_handoff": public_external_handoff(execution),
    }
