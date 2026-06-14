"""Session readiness — OpenHarness-style dry-run checks (MB-9)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from agent_lab.agents.registry import AGENT_IDS

ReadinessVerdict = Literal["ready", "warning", "blocked"]

_CHECK_IDS: dict[str, str] = {
    "cursor": "cursor_bridge",
    "codex": "codex_oauth",
    "claude": "claude_auth",
}


def _next_action_for_row(row: dict[str, Any]) -> str | None:
    remediation = row.get("remediation")
    if isinstance(remediation, list) and remediation:
        return str(remediation[0])
    hint = row.get("hint") or row.get("reason")
    if hint:
        agent = str(row.get("id") or "")
        if agent == "cursor":
            return "Settings → Cursor 재연결"
        if agent == "codex":
            return "Settings → Codex OAuth → 프로필 검증"
        if agent == "claude":
            return "터미널: claude login"
        return str(hint)[:200]
    return None


def _workspace_check(folder: Path | None) -> dict[str, Any]:
    if folder is None or not folder.is_dir():
        return {
            "id": "session_folder",
            "ok": True,
            "detail": None,
            "next": None,
        }
    topic = folder / "topic.txt"
    ok = topic.is_file()
    return {
        "id": "session_folder",
        "ok": ok,
        "detail": None if ok else "session folder incomplete",
        "next": None if ok else "세션 폴더를 다시 열거나 새 세션을 만드세요",
    }


def build_readiness_payload(
    *,
    session_id: str | None = None,
    agent_ids: list[str] | None = None,
    probe_bridge: bool = True,
    probe_cli: bool = True,
) -> dict[str, Any]:
    from agent_lab.agent_preflight import agent_preflight_row
    from agent_lab.run_meta import read_run_meta
    from agent_lab.session import SESSIONS_DIR

    folder: Path | None = None
    run: dict[str, Any] = {}
    if session_id:
        candidate = SESSIONS_DIR / session_id.strip()
        if candidate.is_dir():
            folder = candidate
            run = read_run_meta(candidate)

    from agent_lab.run_control import room_run_in_progress

    if room_run_in_progress():
        # Avoid OAuth/profile probes and headless CLI pings during an active turn.
        probe_bridge = False
        probe_cli = False

    ids = [
        str(a).strip().lower()
        for a in (agent_ids or run.get("agents") or list(AGENT_IDS))
        if str(a).strip()
    ]
    if not ids:
        ids = list(AGENT_IDS)

    checks: list[dict[str, Any]] = [_workspace_check(folder)]
    next_actions: list[str] = []

    for aid in ids:
        if aid not in AGENT_IDS:
            continue
        row = agent_preflight_row(aid, probe_bridge=probe_bridge, probe_cli=probe_cli)
        check_id = _CHECK_IDS.get(aid, f"{aid}_agent")
        ok = bool(row.get("ready"))
        nxt = None if ok else _next_action_for_row(row)
        check: dict[str, Any] = {
            "id": check_id,
            "agent": aid,
            "ok": ok,
            "detail": row.get("reason") or row.get("hint"),
            "next": nxt,
        }
        checks.append(check)
        if nxt:
            next_actions.append(nxt)

    from agent_lab.runtime.adapters.codex import codex_proxy_enabled, probe_codex_proxy

    if codex_proxy_enabled():
        proxy = probe_codex_proxy()
        checks.append(
            {
                "id": "codex_proxy",
                "agent": "codex",
                "ok": bool(proxy.get("ok")),
                "detail": proxy.get("detail"),
                "next": proxy.get("next") or "npx openai-oauth",
            }
        )
        if not proxy.get("ok") and proxy.get("next"):
            next_actions.append(str(proxy["next"]))

    required_fail = [c for c in checks if not c.get("ok")]
    if required_fail:
        verdict: ReadinessVerdict = "blocked"
    elif any(c.get("detail") for c in checks if c.get("ok") and c.get("id") != "session_folder"):
        verdict = "warning"
    else:
        verdict = "ready"

    return {
        "verdict": verdict,
        "session_id": session_id,
        "checks": checks,
        "next_actions": next_actions,
        "agents": ids,
    }
