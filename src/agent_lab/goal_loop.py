"""Mock-first Oracle checks for Human-defined session goals."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.run_meta import patch_run_meta, read_run_meta

DEFAULT_MAX_CHECKS = 5
MAX_MAX_CHECKS = 20

_TRUE = {"1", "true", "yes", "on"}
_BACKTICK_LITERAL = re.compile(r"`([^`\n]+)`")
_WORD = re.compile(r"[A-Za-z0-9_가-힣-]{2,}")
_STOPWORDS = {
    "goal",
    "session",
    "human",
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "목표",
    "세션",
    "달성",
    "완료",
    "하도록",
    "한다",
    "하기",
}


def goal_loop_enabled() -> bool:
    return os.getenv("AGENT_LAB_GOAL_LOOP", "").strip().lower() in _TRUE


def goal_auto_continue_enabled() -> bool:
    return os.getenv("AGENT_LAB_GOAL_AUTO_CONTINUE", "").strip().lower() in _TRUE


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
                "status": "achieved"
                if same_goal and loop.get("status") == "achieved"
                else "open",
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
    transcript = _messages_text(messages_snapshot)
    prompt = _oracle_prompt(goal_text, transcript)
    source = "mock"
    if oracle_call is not None:
        raw = oracle_call(prompt)
        source = "live"
    elif os.getenv("AGENT_LAB_GOAL_ORACLE_LIVE", "").strip().lower() in _TRUE:
        from agent_lab import claude_cli

        raw = claude_cli.invoke("oracle", prompt, scribe=True)
        source = "live"
    else:
        raw = _mock_oracle_response(goal_text, transcript)

    detail = str(raw or "").strip()
    verdict = "pass" if detail.upper().startswith("PASS") else "fail"
    return {
        "at": _now(),
        "verdict": verdict,
        "detail": detail[:500],
        "source": source,
    }


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


def _mock_oracle_response(goal_text: str, transcript: str) -> str:
    haystack = transcript.casefold()
    literals = [m.strip() for m in _BACKTICK_LITERAL.findall(goal_text) if m.strip()]
    if literals:
        missing = [literal for literal in literals if literal.casefold() not in haystack]
        if missing:
            return "FAIL: missing goal literal(s): " + ", ".join(missing)
        return "PASS: all goal literals appear in the session transcript"

    keywords = [
        word
        for word in dict.fromkeys(_WORD.findall(goal_text.casefold()))
        if word not in _STOPWORDS
    ][:8]
    if not keywords:
        return "FAIL: goal needs a backtick literal or concrete keywords"
    matched = [word for word in keywords if word in haystack]
    required = max(1, (len(keywords) + 1) // 2)
    if len(matched) >= required:
        return f"PASS: matched {len(matched)}/{len(keywords)} goal keywords"
    missing = [word for word in keywords if word not in matched]
    return "FAIL: missing goal keyword(s): " + ", ".join(missing[:5])


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


def _oracle_prompt(goal_text: str, transcript: str) -> str:
    return (
        "You are the independent session-goal Oracle. Decide whether the transcript "
        "demonstrates that the Human-defined goal is achieved. Reply with PASS or FAIL "
        "followed by one concise reason.\n\n"
        f"Goal:\n{goal_text}\n\nTranscript:\n{transcript[-12000:] or '(empty)'}"
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
