"""Bind agent-lab session workspace to Kimi Work daimon via workspace.openProject."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.kimi_work_session import get_workspace_path, set_workspace_path


def resolve_workspace_path(
    permissions: dict[str, Any] | None,
    session_folder: str | Path,
) -> Path:
    if permissions:
        from agent_lab.workspace_roots import discuss_primary_workspace

        return discuss_primary_workspace(permissions).resolve()
    return Path(session_folder).expanduser().resolve()


def open_workspace(path: str | Path) -> Any:
    from agent_lab.kimi_control_client import KimiWorkBridgeUnavailable, rpc

    resolved = str(Path(path).expanduser().resolve())
    try:
        return rpc("workspace.openProject", {"path": resolved})
    except KimiWorkBridgeUnavailable:
        return rpc("workspace.addEntry", {"path": resolved})


def ensure_workspace_bound(session_folder: str | Path, workspace_path: str | Path) -> Path:
    """Open daimon project when workspace path changes for this session."""
    resolved = Path(workspace_path).expanduser().resolve()
    existing = get_workspace_path(session_folder)
    if existing == resolved:
        return resolved
    open_workspace(resolved)
    set_workspace_path(session_folder, resolved)
    return resolved
