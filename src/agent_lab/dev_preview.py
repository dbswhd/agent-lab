"""Dev server port management for the Preview tab.

Stores the port in run.json via patch_run_meta(). The frontend opens an
iframe directly to http://localhost:{port}/ — no server-side proxy needed.
This keeps the architecture clean for eventual desktop-app migration where
a native webview can address localhost directly.
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

from agent_lab.run_meta import patch_run_meta, read_run_meta

PORT_MIN = 1024
PORT_MAX = 65534
# Ports reserved by Agent Lab's own processes
_BLOCKED_PORTS: frozenset[int] = frozenset({8765, 5173, 5174, 5175})

# Common dev-server ports (vite/next/cra); 5173 excluded — Agent Lab web dev.
COMMON_DEV_PORTS: tuple[int, ...] = (
    3000,
    3001,
    4173,
    4321,
    5176,
    5177,
    8080,
    8000,
    24678,
)


class DevPreviewError(Exception):
    pass


def resolve_session_workspace_cwd(folder: Path) -> str:
    """Workspace root for dev servers / terminal — binding path or session folder."""
    meta = read_run_meta(folder)
    binding = meta.get("workspace_binding") or {}
    path_str = binding.get("path")
    if path_str:
        p = Path(path_str)
        if p.is_dir():
            return str(p)
    return str(folder)


def _validate_port(port: int) -> None:
    if not isinstance(port, int) or port < PORT_MIN or port > PORT_MAX:
        raise DevPreviewError(f"port {port} out of allowed range {PORT_MIN}–{PORT_MAX}")
    if port in _BLOCKED_PORTS:
        raise DevPreviewError(f"port {port} is reserved by Agent Lab")


def set_dev_server_port(folder: Path, port: int) -> None:
    _validate_port(port)

    def _update(m: dict[str, Any]) -> dict[str, Any]:
        return {**m, "dev_server_port": port}

    patch_run_meta(folder, _update)


def clear_dev_server_port(folder: Path) -> None:
    def _update(m: dict[str, Any]) -> dict[str, Any]:
        return {**m, "dev_server_port": None}

    patch_run_meta(folder, _update)


def get_dev_server_port(folder: Path) -> int | None:
    port = read_run_meta(folder).get("dev_server_port")
    return int(port) if port is not None else None


def is_port_listening(port: int) -> bool:
    """Return True if something is accepting TCP connections on localhost:{port}."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except (OSError, TimeoutError):
        return False


def probe_listening_ports(
    ports: tuple[int, ...] | None = None,
) -> list[int]:
    """Return ports from *ports* that accept TCP on 127.0.0.1 (non-blocked only)."""
    candidates = ports or COMMON_DEV_PORTS
    alive: list[int] = []
    for port in candidates:
        if port in _BLOCKED_PORTS:
            continue
        if is_port_listening(port):
            alive.append(port)
    return alive


def auto_probe_dev_port(folder: Path) -> int | None:
    """Pick the first listening common dev port and persist it in run.json."""
    alive = probe_listening_ports()
    if not alive:
        return None
    port = alive[0]
    set_dev_server_port(folder, port)
    return port


def dev_server_bg_presets(cwd: str) -> list[dict[str, Any]]:
    """Background-task presets that start typical dev servers on non-reserved ports."""
    return [
        {
            "id": "npm-dev",
            "label": "npm run dev",
            "command": ["npm", "run", "dev"],
            "cwd": cwd,
        },
        {
            "id": "vite-3000",
            "label": "vite :3000",
            "command": ["npx", "vite", "--port", "3000", "--strictPort"],
            "cwd": cwd,
        },
        {
            "id": "next-3000",
            "label": "next dev :3000",
            "command": ["npx", "next", "dev", "-p", "3000"],
            "cwd": cwd,
        },
    ]
