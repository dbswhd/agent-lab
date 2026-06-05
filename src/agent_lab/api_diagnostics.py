"""API lifecycle diagnostics for /api/diagnostics and startup troubleshooting."""

from __future__ import annotations

import os
import socket
import time
from pathlib import Path
from typing import Any

_API_STARTED_AT = time.monotonic()
_PROCESS_ID = os.getpid()


def api_uptime_seconds() -> float:
    return max(0.0, time.monotonic() - _API_STARTED_AT)


def boot_log_path() -> Path:
    from agent_lab.app_config import log_dir

    return log_dir() / "agent-lab-boot.log"


def read_boot_log_tail(*, max_lines: int = 20) -> list[str]:
    path = boot_log_path()
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-max_lines:] if len(lines) > max_lines else lines


def mask_tool_path(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    home = str(Path.home())
    if text.startswith(home):
        return "~" + text[len(home) :]
    return text


def probe_tcp_port(host: str, port: int, *, timeout_s: float = 0.35) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return {"listening": True, "host": host, "port": port}
    except OSError as exc:
        return {
            "listening": False,
            "host": host,
            "port": port,
            "error": str(exc)[:200],
        }


def resolved_config_paths() -> dict[str, str | None]:
    from agent_lab.app_config import config_dir, config_path, log_dir

    root = (os.getenv("AGENT_LAB_ROOT") or "").strip()
    sessions = (os.getenv("AGENT_LAB_SESSIONS_DIR") or "").strip()
    dotenv = (os.getenv("DOTENV_PATH") or "").strip()
    home_env = Path.home() / ".agent-lab" / ".env"
    repo_env_candidates = []
    if root:
        repo_env_candidates.append(str(Path(root) / ".env"))
    return {
        "config_dir": str(config_dir()),
        "config_toml": str(config_path()),
        "log_dir": str(log_dir()),
        "boot_log": str(boot_log_path()),
        "dotenv_path": dotenv or None,
        "home_dotenv": str(home_env) if home_env.is_file() else None,
        "repo_dotenv": next(
            (p for p in repo_env_candidates if p and Path(p).is_file()),
            None,
        ),
        "agent_lab_root": root or None,
        "sessions_dir_env": sessions or None,
    }


def agent_tool_paths() -> dict[str, str | None]:
    from agent_lab import claude_cli, codex_cli

    codex = codex_cli.resolve_codex_bin()
    claude = claude_cli.resolve_claude_bin()
    bridge = (os.getenv("CURSOR_SDK_BRIDGE_BIN") or "").strip() or None
    return {
        "CODEX_BIN": mask_tool_path(codex),
        "CLAUDE_BIN": mask_tool_path(claude),
        "CURSOR_SDK_BRIDGE_BIN": mask_tool_path(bridge),
    }


def build_diagnostics_payload() -> dict[str, Any]:
    from agent_lab.app_config import log_dir
    from agent_lab.session import SESSIONS_DIR

    port_raw = (os.getenv("AGENT_LAB_API_PORT") or "8765").strip()
    try:
        port = int(port_raw)
    except ValueError:
        port = 8765

    port_status = probe_tcp_port("127.0.0.1", port)
    paths = resolved_config_paths()
    boot_tail = read_boot_log_tail()

    from agent_lab.goal_loop import goal_loop_enabled
    from agent_lab.plugin_discovery import discover_plugins

    root = Path(os.getenv("AGENT_LAB_ROOT", Path(__file__).resolve().parents[2]))
    discovery = discover_plugins(root, mock=False)
    return {
        "ok": True,
        "pid": _PROCESS_ID,
        "uptime_seconds": round(api_uptime_seconds(), 2),
        "port": port,
        "port_status": port_status,
        "sessions_dir": str(SESSIONS_DIR),
        "paths": paths,
        "agent_tools": agent_tool_paths(),
        "goal_loop_enabled": goal_loop_enabled(),
        "plugins_discovered": len(discovery.get("plugins") or []),
        "plugins_mock": discovery.get("mock", False),
        "boot_log_tail": boot_tail,
        "boot_log_path": str(boot_log_path()),
        "api_log_path": str(log_dir() / "agent-lab-api.log"),
    }
