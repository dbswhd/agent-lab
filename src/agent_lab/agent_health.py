"""Detailed readiness for Cursor / Codex / Claude (health panel + /api/health)."""

from __future__ import annotations

import os
import time
from typing import Any

from agent_lab.agents.registry import AGENT_IDS, label, model_label
from agent_lab.workspace_roots import project_root


def _cursor_sdk_installed() -> bool:
    try:
        import cursor_sdk  # noqa: F401

        return True
    except ImportError:
        return False


_BRIDGE_RETRY_ATTEMPTS = 3
_BRIDGE_RETRY_BACKOFF_S = 0.35


def _check_cursor_bridge_once(workspace: str) -> tuple[str, str | None]:
    from agent_lab.cursor_bridge import cursor_sdk_client, format_cursor_connect_error

    try:
        with cursor_sdk_client(workspace) as client:
            client.ping()  # type: ignore[attr-defined]
        return "ok", None
    except Exception as exc:
        hint = format_cursor_connect_error(exc)
        first = hint.split("\n", 1)[0].strip()
        return "error", first[:240] or str(exc)[:240]


def _check_cursor_bridge(
    workspace: str,
    *,
    retries: int = _BRIDGE_RETRY_ATTEMPTS,
) -> tuple[str, str | None]:
    attempts = max(1, retries)
    last_err: str | None = None
    for attempt in range(attempts):
        bridge, err = _check_cursor_bridge_once(workspace)
        if bridge == "ok":
            return bridge, None
        last_err = err
        if attempt + 1 < attempts:
            time.sleep(_BRIDGE_RETRY_BACKOFF_S * (attempt + 1))
    return "error", last_err


def reconnect_cursor_bridge(*, workspace: str | None = None) -> dict[str, Any]:
    """Invalidate cached bridge and probe with retries (health panel reconnect)."""
    from agent_lab.cursor_bridge import invalidate_workspace

    ws = str(workspace or project_root())
    invalidate_workspace(ws)
    bridge, err = _check_cursor_bridge(ws, retries=_BRIDGE_RETRY_ATTEMPTS)
    row = agent_health_row("cursor", probe_bridge=False)
    row["bridge"] = bridge
    if err:
        row["hint"] = err
    row["ready"] = bool(row["configured"] and bridge == "ok")
    return {
        "ok": bridge == "ok",
        "bridge": bridge,
        "hint": err,
        "agent": row,
    }


def agent_health_row(agent_id: str, *, probe_bridge: bool = False) -> dict[str, Any]:
    aid = agent_id.strip().lower()
    row: dict[str, Any] = {
        "id": aid,
        "label": label(aid),  # type: ignore[arg-type]
        "model": model_label(aid),  # type: ignore[arg-type]
        "configured": False,
        "ready": False,
        "bridge": "n/a",
        "hint": None,
    }

    if aid == "cursor":
        has_key = bool(os.getenv("CURSOR_API_KEY", "").strip())
        sdk = _cursor_sdk_installed()
        row["configured"] = has_key and sdk
        if not has_key:
            row["hint"] = "CURSOR_API_KEY 없음 — .env 확인"
        elif not sdk:
            row["hint"] = "cursor-sdk 미설치 — pip install -e '.[cursor]'"
        elif probe_bridge:
            bridge, err = _check_cursor_bridge(str(project_root()))
            row["bridge"] = bridge
            if err:
                row["hint"] = err
            row["ready"] = row["configured"] and bridge == "ok"
        else:
            row["bridge"] = "unknown"
            row["ready"] = row["configured"]
        return row

    if aid == "codex":
        from agent_lab import codex_cli

        bin_path = codex_cli.resolve_codex_bin()
        row["configured"] = bin_path is not None
        row["ready"] = row["configured"]
        row["bridge"] = "n/a"
        if not bin_path:
            row["hint"] = "codex CLI 없음 — codex login (CODEX_BIN 설정 가능)"
        else:
            row["detail"] = bin_path
        return row

    if aid == "claude":
        from agent_lab import claude_cli

        bin_path = claude_cli.resolve_claude_bin()
        row["configured"] = bin_path is not None
        row["ready"] = row["configured"]
        row["bridge"] = "n/a"
        if not bin_path:
            row["hint"] = "claude CLI 없음 — claude login (CLAUDE_BIN 설정 가능)"
        else:
            row["detail"] = bin_path
        return row

    row["hint"] = "unknown agent"
    return row


def build_agent_health(
    *,
    probe_bridge: bool = False,
    probe_preflight: bool = False,
) -> list[dict[str, Any]]:
    if probe_preflight:
        from agent_lab.agent_preflight import build_agent_preflight

        return build_agent_preflight(probe_bridge=probe_bridge, probe_cli=True)
    return [agent_health_row(aid, probe_bridge=probe_bridge) for aid in AGENT_IDS]


def build_health_payload(
    *,
    probe_bridge: bool = False,
    probe_preflight: bool = False,
) -> dict[str, Any]:
    from agent_lab import claude_cli, codex_cli
    from agent_lab.context_limits import all_limits_for_api, efficiency_mode_default
    from agent_lab.invoke import model_name, provider
    from agent_lab.room import DEFAULT_AGENT_PARALLEL_ROUNDS, MAX_AGENT_PARALLEL_ROUNDS
    from agent_lab.room_consensus import max_consensus_calls, max_consensus_rounds
    from agent_lab.session import SESSIONS_DIR

    agents = build_agent_health(
        probe_bridge=probe_bridge,
        probe_preflight=probe_preflight,
    )
    ready_ids = [a["id"] for a in agents if a.get("ready")]

    return {
        "ok": True,
        "preflight": probe_preflight,
        "api": {"ok": True, "port": 8765},
        "provider": provider() or None,
        "model": model_name() if provider() else None,
        "codex_cli": codex_cli.is_available(),
        "claude_cli": claude_cli.is_available(),
        "agents": agents,
        "agents_ready": ready_ids,
        "sessions_dir": str(SESSIONS_DIR),
        "efficiency_mode_default": efficiency_mode_default(),
        "room": {
            "default_agent_parallel_rounds": DEFAULT_AGENT_PARALLEL_ROUNDS,
            "max_agent_parallel_rounds": MAX_AGENT_PARALLEL_ROUNDS,
            "max_consensus_rounds": max_consensus_rounds(),
            "max_consensus_calls": max_consensus_calls(),
        },
        "context": all_limits_for_api(),
    }
