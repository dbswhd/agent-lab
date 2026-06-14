"""Detailed readiness for Cursor / Codex / Claude (health panel + /api/health)."""

from __future__ import annotations

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


def reconnect_claude_auth() -> dict[str, Any]:
    """Invalidate cached Claude OAuth checks and re-probe (health panel reconnect)."""
    from agent_lab import claude_cli

    claude_cli.invalidate_claude_auth_cache()
    auth_ok, auth_detail = claude_cli.claude_auth_logged_in(use_cache=False)
    probe_ok = False
    probe_detail: str | None = None
    if auth_ok:
        probe_ok, probe_detail = claude_cli.probe_auth(use_cache=False)

    ok = auth_ok and probe_ok
    hint = probe_detail or auth_detail
    row = agent_health_row("claude", probe_bridge=False)
    if not ok:
        row["ready"] = False
        row["hint"] = hint
        row["reason"] = hint
        row["failure_code"] = "claude_auth_failed"
        row["remediation"] = claude_cli.auth_failure_remediation(hint or "")
    else:
        row["ready"] = True
        row["hint"] = None

    return {
        "ok": ok,
        "auth_ok": auth_ok,
        "probe_ok": probe_ok,
        "hint": hint,
        "remediation": row.get("remediation"),
        "agent": row,
    }


def reconnect_cursor_bridge(*, workspace: str | None = None) -> dict[str, Any]:
    """Invalidate cached bridge and probe with retries (health panel reconnect)."""
    from agent_lab.cursor_bridge import cursor_bridge_failure_payload, invalidate_workspace

    ws = str(workspace or project_root())
    invalidate_workspace(ws)
    bridge, err = _check_cursor_bridge(ws, retries=_BRIDGE_RETRY_ATTEMPTS)
    row = agent_health_row("cursor", probe_bridge=False)
    row["bridge"] = bridge
    if err:
        row["hint"] = err
        row.update(cursor_bridge_failure_payload(reason=err))
    row["ready"] = bool(row["configured"] and bridge == "ok")
    return {
        "ok": bridge == "ok",
        "bridge": bridge,
        "hint": err,
        "agent": row,
    }


def _capability_fields(agent_id: str, run_meta: dict[str, Any] | None) -> dict[str, Any]:
    from agent_lab.room_agent_capabilities import get_agent_capabilities

    cap = get_agent_capabilities(run_meta).get(agent_id.strip().lower()) or {}
    tools = cap.get("tools") or []
    label_text = str(cap.get("label") or "").strip()
    out: dict[str, Any] = {}
    if tools:
        out["capabilities"] = tools
    if label_text:
        out["capability_label"] = label_text
    return out


def _model_readiness_fields(agent_id: str) -> dict[str, Any]:
    from agent_lab.model_policy import model_readiness

    readiness = model_readiness(agent_id)
    if readiness is None:
        return {}
    return {
        "model_provider": readiness.provider,
        "team_ready": readiness.team_ready,
        "loop_ready": readiness.loop_ready,
        "loop_blockers": list(readiness.loop_blockers),
    }


def agent_health_row(
    agent_id: str,
    *,
    probe_bridge: bool = False,
    run_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    aid = agent_id.strip().lower()
    row: dict[str, Any] = {
        "id": aid,
        "label": label(aid),  # type: ignore[arg-type]
        "model": model_label(aid),  # type: ignore[arg-type]
        "configured": False,
        "ready": False,
        "bridge": "n/a",
        "hint": None,
        **_capability_fields(aid, run_meta),
        **_model_readiness_fields(aid),
    }

    if aid == "cursor":
        from agent_lab.credential_store import provider_has_credentials
        from agent_lab.cursor_bridge import cursor_bridge_failure_payload

        has_key = provider_has_credentials("cursor")
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
                row.update(cursor_bridge_failure_payload(reason=err))
            row["ready"] = row["configured"] and bridge == "ok"
        else:
            row["bridge"] = "unknown"
            row["ready"] = row["configured"]
        return row

    if aid == "codex":
        from agent_lab import codex_cli
        from agent_lab.codex_oauth import codex_oauth_ready

        bin_path = codex_cli.resolve_codex_bin()
        row["configured"] = bin_path is not None
        row["bridge"] = "n/a"
        row["auth_mode"] = "oauth"
        if not bin_path:
            row["ready"] = False
            row["hint"] = "codex CLI 없음 — codex login (CODEX_BIN 설정 가능)"
            return row
        row["detail"] = bin_path
        auth_ok, auth_detail = codex_oauth_ready()
        if not auth_ok:
            row["ready"] = False
            row["hint"] = auth_detail or "codex OAuth 미등록 — codex login 후 Settings에서 캡처"
            row["reason"] = row["hint"]
            row["failure_code"] = "codex_auth_failed"
            return row
        row["ready"] = True
        return row

    if aid == "claude":
        from agent_lab import claude_cli

        bin_path = claude_cli.resolve_claude_bin()
        row["configured"] = bin_path is not None
        row["bridge"] = "n/a"
        if not bin_path:
            row["ready"] = False
            row["hint"] = "claude CLI 없음 — claude auth login (CLAUDE_BIN 설정 가능)"
            return row
        row["detail"] = bin_path
        row["auth_mode"] = "oauth"
        auth_ok, auth_detail = claude_cli.claude_auth_logged_in()
        if not auth_ok:
            row["ready"] = False
            row["hint"] = auth_detail or "claude OAuth 미로그인 — claude auth login"
            row["reason"] = row["hint"]
            row["failure_code"] = "claude_auth_failed"
            row["remediation"] = claude_cli.auth_failure_remediation(auth_detail or "")
            return row
        row["ready"] = True
        return row

    row["hint"] = "unknown agent"
    return row


def build_agent_health(
    *,
    probe_bridge: bool = False,
    probe_preflight: bool = False,
    run_meta: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if probe_preflight:
        from agent_lab.agent_preflight import build_agent_preflight

        rows = build_agent_preflight(probe_bridge=probe_bridge, probe_cli=True)
        for row in rows:
            agent_id = str(row.get("id") or "")
            row.update(_capability_fields(agent_id, run_meta))
            row.update(_model_readiness_fields(agent_id))
        return rows
    return [agent_health_row(aid, probe_bridge=probe_bridge, run_meta=run_meta) for aid in AGENT_IDS]


def build_health_payload(
    *,
    probe_bridge: bool = False,
    probe_preflight: bool = False,
    run_meta: dict[str, Any] | None = None,
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
        run_meta=run_meta,
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
