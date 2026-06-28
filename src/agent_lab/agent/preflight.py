"""Lightweight CLI / bridge probes for room send gates and health panel."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from agent_lab.agents.registry import AGENT_IDS, label, model_label


def cursor_bridge_mode() -> str:
    """external = CURSOR_SDK_BRIDGE_URL set; auto = launch via SDK."""
    if (os.getenv("CURSOR_SDK_BRIDGE_URL") or "").strip():
        return "external"
    return "auto"


def _bridge_bin_path() -> Path | None:
    raw = (os.getenv("CURSOR_SDK_BRIDGE_BIN") or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    return p if p.is_file() else None


def _mark_cursor_bridge_degraded(row: dict[str, Any], reason: str) -> None:
    from agent_lab.cursor_bridge import cursor_bridge_failure_payload

    row.update(cursor_bridge_failure_payload(reason=reason))
    row["hint"] = reason
    row["reason"] = reason


def _probe_cli_version(
    bin_path: str,
    *,
    timeout_sec: float = 12.0,
    env: dict[str, str] | None = None,
) -> tuple[bool, str | None]:
    try:
        result = subprocess.run(
            [bin_path, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=env,
        )
    except FileNotFoundError:
        return False, f"CLI 없음: {bin_path}"
    except subprocess.TimeoutExpired:
        return False, f"CLI --version 시간 초과 ({int(timeout_sec)}s)"
    except OSError as exc:
        return False, str(exc)[:200]
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:200]
        return False, detail or f"exit {result.returncode}"
    line = (result.stdout or result.stderr or "").strip().splitlines()
    return True, (line[0][:120] if line else None)


def format_codex_exec_error(detail: str) -> str:
    """Human-readable Codex failure (incl. os error 2 / missing path)."""
    low = detail.lower()
    if "os error 2" in low or ("no such file or directory" in low and "codex" not in low):
        return (
            "Codex가 참조한 파일/경로를 찾을 수 없습니다 (os error 2). "
            "workspace·샌드박스 확인 — CODEX_ROOM_WORKSPACE_WRITE, docs/STABILITY.md"
        )
    if "enoent" in low and "codex" in low:
        return "Codex CLI를 찾을 수 없습니다. codex login 또는 CODEX_BIN 절대경로 설정"
    return detail


def agent_preflight_row(
    agent_id: str,
    *,
    probe_bridge: bool = True,
    probe_cli: bool = True,
) -> dict[str, Any]:
    """One agent readiness row: { id, ready, reason, ... }."""
    from agent_lab import claude_cli, codex_cli
    from agent_lab.agent.health import agent_health_row

    aid = agent_id.strip().lower()
    _known = set(AGENT_IDS) | {"kimi", "kimi_work", "local"}
    if aid not in _known:
        return {
            "id": aid,
            "label": aid,
            "model": "",
            "configured": False,
            "ready": False,
            "bridge": "n/a",
            "bridge_mode": "n/a",
            "hint": "unknown agent",
            "reason": "unknown agent",
            "detail": None,
        }
    base = agent_health_row(aid, probe_bridge=False)
    row: dict[str, Any] = {
        "id": aid,
        "label": label(aid),  # type: ignore[arg-type]
        "model": model_label(aid),  # type: ignore[arg-type]
        "configured": base["configured"],
        "ready": False,
        "bridge": base.get("bridge", "n/a"),
        "bridge_mode": "n/a",
        "hint": base.get("hint"),
        "reason": None,
        "detail": base.get("detail"),
    }

    if aid == "cursor":
        row["bridge_mode"] = cursor_bridge_mode()
        if not row["configured"]:
            row["reason"] = row["hint"] or "CURSOR_API_KEY 또는 cursor-sdk 필요"
            return row
        if row["bridge_mode"] == "external":
            if probe_bridge:
                from agent_lab.agent.health import _check_cursor_bridge
                from agent_lab.workspace.roots import project_root

                bridge, err = _check_cursor_bridge(str(project_root()))
                row["bridge"] = bridge
                if err:
                    row["hint"] = err
                if bridge != "ok":
                    _mark_cursor_bridge_degraded(
                        row,
                        err or "external bridge 연결 실패",
                    )
                    return row
            row["ready"] = True
            row["reason"] = "external bridge"
            return row
        bridge_bin = _bridge_bin_path()
        if probe_cli and bridge_bin is None:
            row["reason"] = "CURSOR_SDK_BRIDGE_BIN 없음 — ~/.agent-lab/.env 절대경로 설정"
            row["fallback"] = "Cursor 제외 후 Codex/Claude 로컬 CLI로 전송하거나 bridge 설정 후 재시도"
            row["remediation"] = [
                "CURSOR_SDK_BRIDGE_BIN 절대경로 설정",
                "Cursor 앱 실행",
                "상태 패널에서 재연결",
            ]
            row["failure_code"] = "cursor_bridge_bin_missing"
            row["degraded"] = True
            return row
        if probe_bridge:
            from agent_lab.agent.health import _check_cursor_bridge
            from agent_lab.workspace.roots import project_root

            bridge, err = _check_cursor_bridge(str(project_root()))
            row["bridge"] = bridge
            if err:
                row["hint"] = err
            if bridge != "ok":
                _mark_cursor_bridge_degraded(row, err or "bridge ping 실패")
                return row
        row["ready"] = True
        row["reason"] = None
        return row

    if aid == "codex":
        from agent_lab.runtime_paths import configure_subprocess_path

        if probe_cli:
            configure_subprocess_path()
        bin_path = codex_cli.resolve_codex_bin()
        row["configured"] = bin_path is not None
        if not bin_path:
            row["reason"] = "codex CLI 없음 — codex login (CODEX_BIN)"
            row["hint"] = row["reason"]
            return row
        row["detail"] = bin_path
        if probe_cli:
            ok, ver = _probe_cli_version(bin_path, env=codex_cli._codex_env())
            if not ok:
                row["reason"] = ver or "codex --version 실패"
                row["hint"] = row["reason"]
                return row
            if ver:
                row["detail"] = ver
            from agent_lab.codex_oauth import codex_oauth_ready

            auth_ok, auth_detail = codex_oauth_ready()
            if not auth_ok:
                row["reason"] = auth_detail or "codex OAuth 미등록"
                row["hint"] = row["reason"]
                row["failure_code"] = "codex_auth_failed"
                row["remediation"] = [
                    "터미널: codex login (ChatGPT 계정)",
                    "Settings → Codex OAuth → 메인/서브 계정 캡처",
                    "한도 초과 시 서브 계정으로 자동 전환",
                ]
                return row
            from agent_lab.codex_oauth import probe_captured_profiles

            profiles = probe_captured_profiles()
            if profiles:
                row["oauth_profiles"] = profiles
                bad = [p for p in profiles if not p.get("ok")]
                if bad:
                    names = ", ".join(str(p.get("label") or p.get("slot")) for p in bad)
                    row["reason"] = f"Codex OAuth 프로필 검증 실패: {names}"
                    row["hint"] = row["reason"]
                    row["failure_code"] = "codex_oauth_profile_invalid"
                    row["remediation"] = [
                        "Settings → Codex OAuth → 프로필 검증",
                        "실패한 계정으로 codex login 후 재캡처",
                    ]
                    return row
        row["ready"] = True
        return row

    if aid == "claude":
        from agent_lab.runtime_paths import configure_subprocess_path

        if probe_cli:
            configure_subprocess_path()
        bin_path = claude_cli.resolve_claude_bin()
        row["configured"] = bin_path is not None
        if not bin_path:
            row["reason"] = "claude CLI 없음 — claude login (CLAUDE_BIN)"
            row["hint"] = row["reason"]
            return row
        row["detail"] = bin_path
        if probe_cli:
            ok, ver = _probe_cli_version(bin_path, env=claude_cli._claude_env())
            if not ok:
                row["reason"] = ver or "claude --version 실패"
                row["hint"] = row["reason"]
                return row
            if ver:
                row["detail"] = ver
            auth_ok, auth_detail = claude_cli.claude_auth_logged_in(use_cache=True)
            if not auth_ok:
                row["reason"] = auth_detail or "claude OAuth 미로그인 — claude auth login"
                row["hint"] = row["reason"]
                row["failure_code"] = "claude_auth_failed"
                row["remediation"] = claude_cli.auth_failure_remediation(auth_detail or "")
                row["fallback"] = "Claude 칩을 끄고 Cursor·Codex만 전송하거나 터미널에서 claude login 후 재시도"
                return row
            probe_ok, probe_detail = claude_cli.probe_auth(use_cache=True)
            if not probe_ok:
                row["reason"] = probe_detail or "claude headless auth failed"
                row["hint"] = row["reason"]
                row["failure_code"] = "claude_auth_failed"
                row["remediation"] = claude_cli.auth_failure_remediation(probe_detail or "")
                row["fallback"] = (
                    "Claude 칩을 끄고 Cursor·Codex만 전송하거나 "
                    "상태 패널 → Claude 재연결 / 터미널 `claude logout && claude login`"
                )
                return row
        row["ready"] = True
        return row

    if aid in {"kimi", "kimi_work", "local"}:
        health = agent_health_row(aid, probe_bridge=probe_bridge)
        row["configured"] = health.get("configured", False)
        row["ready"] = bool(health.get("ready"))
        row["bridge"] = health.get("bridge", row["bridge"])
        row["hint"] = health.get("hint")
        row["reason"] = health.get("hint") if not row["ready"] else None
        row["detail"] = health.get("detail")
        row["failure_code"] = health.get("failure_code")
        row["fallback"] = health.get("fallback")
        row["remediation"] = health.get("remediation")
        row["degraded"] = health.get("degraded", False)
        return row

    row["reason"] = "unknown agent"
    return row


def build_agent_preflight(
    *,
    probe_bridge: bool = True,
    probe_cli: bool = True,
) -> list[dict[str, Any]]:
    ids = list(AGENT_IDS)
    from agent_lab.agent.roster import dynamic_room_enabled

    if dynamic_room_enabled():
        for extra in ("kimi", "kimi_work", "local"):
            if extra not in ids:
                ids.append(extra)  # type: ignore[arg-type]
    return [agent_preflight_row(aid, probe_bridge=probe_bridge, probe_cli=probe_cli) for aid in ids]


def agents_not_ready(
    agent_ids: list[str] | None,
    *,
    probe_bridge: bool = True,
    probe_cli: bool = True,
) -> list[dict[str, Any]]:
    """Rows for requested agents that failed preflight."""
    from agent_lab.agents.registry import available_agents

    ids = [a.strip().lower() for a in (agent_ids or available_agents()) if str(a).strip()]
    bad: list[dict[str, Any]] = []
    for aid in ids:
        row = agent_preflight_row(aid, probe_bridge=probe_bridge, probe_cli=probe_cli)
        if not row.get("ready"):
            bad.append(
                {
                    "id": row["id"],
                    "ready": False,
                    "reason": row.get("reason") or row.get("hint") or "not ready",
                    "hint": row.get("hint"),
                    "failure_code": row.get("failure_code"),
                    "fallback": row.get("fallback"),
                    "remediation": row.get("remediation"),
                    "degraded": row.get("degraded", False),
                }
            )
    return bad


def validate_agents_for_run(agent_ids: list[str] | None) -> None:
    """Raise ValueError with structured detail if any agent is not ready."""
    bad = agents_not_ready(agent_ids)
    if bad:
        lines = [f"{r['id']}: {r['reason']}" for r in bad]
        raise ValueError("; ".join(lines))
