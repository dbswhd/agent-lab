"""Live soak — launchd daemon + tunnel mission-wake ingress (Tier E)."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import urllib.error
import urllib.request
from typing import Any

from agent_lab.gateway.hybrid_relay import wake_hint_for_envelope
from agent_lab.live_execute_spike import _now

_LAUNCHD_LABEL = "com.agentlab.serve-daemon"

_REQUIRED_CHECKS = frozenset(
    {
        "daemon_health_ok",
        "daemon_scheduler_enabled",
        "local_mission_wake_ok",
        "scheduler_tick_updated",
        "hybrid_wake_hint_ok",
    }
)

_OPTIONAL_TUNNEL_CHECKS = frozenset({"tunnel_wake_ok"})


def _http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout_s: int = 10,
) -> tuple[int, dict[str, Any] | None, str | None]:
    req = urllib.request.Request(
        url,
        data=body,
        headers=headers or {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=max(1, timeout_s)) as resp:
            raw = resp.read().decode("utf-8")
            parsed: dict[str, Any] | None = None
            if raw.strip():
                try:
                    loaded = json.loads(raw)
                    if isinstance(loaded, dict):
                        parsed = loaded
                except json.JSONDecodeError:
                    parsed = None
            return resp.status, parsed, None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        parsed: dict[str, Any] | None = None
        if raw.strip():
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    parsed = loaded
            except json.JSONDecodeError:
                parsed = None
        return exc.code, parsed, str(exc)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, None, str(exc)


def launchd_agent_loaded(label: str = _LAUNCHD_LABEL) -> bool:
    if platform.system() != "Darwin":
        return False
    try:
        result = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def fetch_daemon_health(api_base: str) -> tuple[bool, dict[str, Any] | None, str | None]:
    status, body, err = _http_json(f"{api_base.rstrip('/')}/api/health/daemon")
    if err:
        return False, body, err
    return 200 <= status < 300 and isinstance(body, dict), body, err


def post_mission_wake(
    *,
    wake_url: str,
    scheduler_token: str | None = None,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    headers = {"Content-Type": "application/json"}
    token = (scheduler_token or os.getenv("AGENT_LAB_SCHEDULER_HOOK_TOKEN") or "").strip()
    if token:
        headers["X-Agent-Lab-Scheduler-Token"] = token
    status, body, err = _http_json(
        wake_url,
        method="POST",
        headers=headers,
        body=b"{}",
    )
    ok = 200 <= status < 300 and isinstance(body, dict) and body.get("ok") is True
    if not ok and err is None and isinstance(body, dict):
        err = str(body.get("detail") or body)
    return ok, body, err


def check_hybrid_wake_hint(*, wake_url: str) -> bool:
    hybrid = {"wake_url": wake_url, "wake_enabled": True}
    hint = wake_hint_for_envelope(hybrid, event="schedule_tick", online=False)
    return hint is not None and hint.get("url") == wake_url


def run_live_tunnel_launchd_soak(
    *,
    api_base: str | None = None,
    tunnel_wake_url: str | None = None,
    require_launchd: bool = False,
    skip_launchd: bool = False,
) -> dict[str, Any]:
    """
    Tier E soak: launchd serve daemon + local/tunnel mission-wake → scheduler tick.

    Requires a running API (`serve --daemon` or launchd). Does not call Cursor SDK.
    """
    base = (api_base or os.getenv("AGENT_LAB_SOAK_API_BASE") or "http://127.0.0.1:8765").rstrip("/")
    tunnel = (tunnel_wake_url or os.getenv("AGENT_LAB_TUNNEL_WAKE_URL") or os.getenv("TUNNEL_WAKE_URL") or "").strip()
    local_wake = f"{base}/api/hooks/mission-wake"

    report: dict[str, Any] = {
        "kind": "live_tunnel_launchd",
        "started_at": _now(),
        "status": "skipped",
        "checks": {},
        "api_base": base,
        "local_wake_url": local_wake,
        "tunnel_wake_url": tunnel or None,
        "daemon_before": None,
        "daemon_after": None,
        "local_wake": None,
        "tunnel_wake": None,
        "hybrid": None,
        "errors": [],
        "warnings": [],
    }
    checks: dict[str, bool] = {}

    if os.getenv("AGENT_LAB_SKIP_LIVE", "").strip() in {"1", "true", "yes"}:
        report["errors"].append("AGENT_LAB_SKIP_LIVE set")
        report["finished_at"] = _now()
        return report

    if not skip_launchd and platform.system() == "Darwin":
        checks["launchd_loaded"] = launchd_agent_loaded()
        if require_launchd and not checks["launchd_loaded"]:
            report["errors"].append(f"launchd agent {_LAUNCHD_LABEL} not loaded")
    elif skip_launchd:
        report["warnings"].append("launchd check skipped (AGENT_LAB_SOAK_SKIP_LAUNCHD=1)")
    else:
        report["warnings"].append("launchd check skipped (non-macOS)")

    health_ok, health_body, health_err = fetch_daemon_health(base)
    checks["daemon_health_ok"] = health_ok
    report["daemon_before"] = health_body
    if not health_ok:
        report["errors"].append(
            health_err or "daemon health unavailable — start `make install-serve-daemon` or serve --daemon"
        )
        report["checks"] = checks
        report["status"] = "skipped"
        report["finished_at"] = _now()
        return report

    checks["daemon_scheduler_enabled"] = bool(
        isinstance(health_body, dict) and health_body.get("scheduler_enabled") is True
    )
    if not checks["daemon_scheduler_enabled"]:
        report["warnings"].append("scheduler_enabled false in daemon_state — wake may still work")

    tick_before = str(health_body.get("last_scheduler_tick_at") or "") if isinstance(health_body, dict) else ""

    local_ok, local_body, local_err = post_mission_wake(wake_url=local_wake)
    checks["local_mission_wake_ok"] = local_ok
    report["local_wake"] = {"ok": local_ok, "body": local_body, "error": local_err}
    if not local_ok:
        report["errors"].append(local_err or "local mission-wake failed")

    _, health_after, _ = fetch_daemon_health(base)
    report["daemon_after"] = health_after
    tick_after = str(health_after.get("last_scheduler_tick_at") or "") if isinstance(health_after, dict) else ""
    checks["scheduler_tick_updated"] = bool(tick_after and tick_after != tick_before) or local_ok
    if local_ok and tick_before == tick_after:
        report["warnings"].append("last_scheduler_tick_at unchanged after wake (tick may be noop)")

    checks["hybrid_wake_hint_ok"] = check_hybrid_wake_hint(wake_url=local_wake)
    report["hybrid"] = {"wake_hint_ok": checks["hybrid_wake_hint_ok"]}

    if tunnel:
        tunnel_url = (
            tunnel if tunnel.endswith("/api/hooks/mission-wake") else f"{tunnel.rstrip('/')}/api/hooks/mission-wake"
        )
        tunnel_ok, tunnel_body, tunnel_err = post_mission_wake(wake_url=tunnel_url)
        checks["tunnel_wake_ok"] = tunnel_ok
        report["tunnel_wake"] = {
            "url": tunnel_url,
            "ok": tunnel_ok,
            "body": tunnel_body,
            "error": tunnel_err,
        }
        if not tunnel_ok:
            report["errors"].append(tunnel_err or "tunnel mission-wake failed")
    else:
        report["warnings"].append(
            "tunnel_wake_ok not tested — set AGENT_LAB_TUNNEL_WAKE_URL (cloudflared/ngrok public URL)"
        )

    failed = [name for name in _REQUIRED_CHECKS if not checks.get(name)]
    if tunnel:
        failed.extend(name for name in _OPTIONAL_TUNNEL_CHECKS if not checks.get(name))

    report["checks"] = checks
    if failed:
        report["status"] = "no_go"
        report["errors"].append(f"failed checks: {', '.join(failed)}")
    else:
        report["status"] = "go"
    report["finished_at"] = _now()
    return report


def format_tunnel_soak_lines(report: dict[str, Any]) -> list[str]:
    lines = [
        f"Tier E tunnel+launchd soak: {report.get('status', 'unknown').upper()}",
        f"  api: {report.get('api_base')}",
    ]
    if report.get("tunnel_wake_url"):
        lines.append(f"  tunnel: {report.get('tunnel_wake_url')}")
    checks = report.get("checks") or {}
    for key in sorted(checks):
        mark = "OK" if checks[key] else "FAIL"
        lines.append(f"  {key}: {mark}")
    for warning in report.get("warnings") or []:
        lines.append(f"  warn: {warning}")
    for err in report.get("errors") or []:
        lines.append(f"  error: {err}")
    return lines
