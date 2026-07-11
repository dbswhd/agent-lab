"""Mock-first Oracle checks for Human-defined session goals."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from agent_lab.time_utils import utc_now_iso as _now
from agent_lab.env_flags import env_bool
from agent_lab.run.meta import patch_run_meta, read_run_meta

DEFAULT_MAX_CHECKS = 5
MAX_MAX_CHECKS = 20


def goal_loop_enabled() -> bool:
    return env_bool("AGENT_LAB_GOAL_LOOP")


def goal_auto_continue_enabled() -> bool:
    return env_bool("AGENT_LAB_GOAL_AUTO_CONTINUE")


def set_session_goal(
    session_folder: Path,
    goal_text: str,
    *,
    max_checks: int = DEFAULT_MAX_CHECKS,
) -> dict[str, Any]:
    text = goal_text.strip()
    if not text:
        raise ValueError("session goal text is required")
    limit = max(1, min(int(max_checks), MAX_MAX_CHECKS))
    now = _now()

    def _set(run: dict[str, Any]) -> dict[str, Any]:
        previous = run.get("session_goal") or {}
        same_goal = str(previous.get("text") or "").strip() == text
        loop = dict(run.get("goal_loop") or {}) if same_goal else {}
        loop.update(
            {
                "enabled": True,
                "max_checks": limit,
                "checks": list(loop.get("checks") or []),
                "status": "achieved" if same_goal and loop.get("status") == "achieved" else "open",
            }
        )
        loop.pop("auto_continue_pending", None)
        loop.pop("continue_prompt", None)
        if loop["status"] != "achieved":
            loop.pop("achieved_at", None)
        run["session_goal"] = {
            "text": text,
            "set_at": previous.get("set_at") if same_goal else now,
            "updated_at": now,
            "set_by": "human",
        }
        run["goal_loop"] = loop
        return run

    updated = patch_run_meta(session_folder, _set)
    return {
        "session_goal": updated["session_goal"],
        "goal_loop": updated["goal_loop"],
    }


def goal_oracle_check(
    session_folder: Path,
    goal_text: str,
    messages_snapshot: Iterable[Any],
    *,
    oracle_call: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Evaluate a session goal independently from execute verification."""
    from agent_lab.oracle_core import (
        build_goal_oracle_prompt,
        build_oracle_result,
        invoke_oracle,
        mock_goal_oracle_response,
        oracle_live_enabled,
        resolved_oracle_model,
        session_oracle_context,
    )
    from agent_lab.run.meta import read_run_meta
    from agent_lab.trading_mission.trading_goal_oracle import (
        is_trading_mission_run,
        mock_trading_goal_oracle_response,
    )

    run = read_run_meta(session_folder)
    if is_trading_mission_run(run):
        raw = mock_trading_goal_oracle_response(session_folder, goal_text)
        result = build_oracle_result(
            raw=raw,
            source="trading_artifact",
            kind="goal",
            goal_text=goal_text,
        )
        result["at"] = _now()
        return result

    transcript = _messages_text(messages_snapshot)
    prompt = build_goal_oracle_prompt(
        goal_text,
        transcript,
        extra_evidence=session_oracle_context(session_folder),
    )
    if oracle_call is not None:
        raw, source = invoke_oracle("goal", prompt, oracle_call=oracle_call)
    elif oracle_live_enabled(goal=True):
        raw, source = invoke_oracle("goal", prompt, session_folder=session_folder)
    else:
        raw = mock_goal_oracle_response(goal_text, transcript)
        source = "mock"

    result = build_oracle_result(
        raw=raw,
        source=source,
        kind="goal",
        goal_text=goal_text,
        model=resolved_oracle_model("goal") if source == "live" else None,
    )
    result["at"] = _now()
    return result


def check_session_goal(
    session_folder: Path,
    messages_snapshot: Iterable[Any] | None = None,
    *,
    oracle_call: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    run = read_run_meta(session_folder)
    goal = run.get("session_goal") or {}
    loop = run.get("goal_loop") or {}
    goal_text = str(goal.get("text") or "").strip()
    if not goal_text:
        return {"checked": False, "reason": "goal_missing"}
    if not loop.get("enabled"):
        return {"checked": False, "reason": "goal_loop_disabled"}
    if loop.get("status") in {"achieved", "abandoned"}:
        return {
            "checked": False,
            "reason": f"goal_{loop.get('status')}",
            "session_goal": goal,
            "goal_loop": loop,
        }

    checks = list(loop.get("checks") or [])
    max_checks = max(1, min(int(loop.get("max_checks") or DEFAULT_MAX_CHECKS), MAX_MAX_CHECKS))
    if len(checks) >= max_checks:
        return {
            "checked": False,
            "reason": "max_checks_reached",
            "session_goal": goal,
            "goal_loop": loop,
        }

    snapshot = list(messages_snapshot) if messages_snapshot is not None else _read_chat(session_folder)
    check = goal_oracle_check(
        session_folder,
        goal_text,
        snapshot,
        oracle_call=oracle_call,
    )

    def _record(current: dict[str, Any]) -> dict[str, Any]:
        current_loop = dict(current.get("goal_loop") or {})
        current_checks = list(current_loop.get("checks") or [])
        current_checks.append(check)
        current_loop["checks"] = current_checks
        current_loop["last_check"] = check
        current_loop["status"] = "achieved" if check["verdict"] == "pass" else "open"
        if check["verdict"] == "pass":
            current_loop["achieved_at"] = check["at"]
            current_loop.pop("auto_continue_pending", None)
            current_loop.pop("continue_prompt", None)
        else:
            current_loop.pop("achieved_at", None)
            if goal_auto_continue_enabled():
                current_loop["auto_continue_pending"] = True
                current_loop["continue_prompt"] = (
                    f"세션 목표가 아직 미달성입니다. 한 턴 더 토론해 주세요: {check['detail']}"
                )
        current["goal_loop"] = current_loop
        return current

    updated = patch_run_meta(session_folder, _record)
    return {
        "checked": True,
        "check": check,
        "session_goal": updated.get("session_goal"),
        "goal_loop": updated.get("goal_loop"),
    }


def maybe_check_session_goal_after_turn(
    session_folder: Path,
    messages_snapshot: Iterable[Any],
) -> dict[str, Any] | None:
    if not goal_loop_enabled():
        return None
    result = check_session_goal(session_folder, messages_snapshot)
    return result if result.get("checked") else None


def _messages_text(messages: Iterable[Any]) -> str:
    rows: list[str] = []
    for message in messages:
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


def _read_chat(session_folder: Path) -> list[dict[str, Any]]:
    path = session_folder / "chat.jsonl"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows
