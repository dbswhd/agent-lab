from __future__ import annotations

import platform
import subprocess

from agent_lab.subprocess_env import subprocess_env


def _escape_applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def pick_folder_macos(
    *,
    default_path: str | None = None,
    title: str = "작업 폴더 선택",
) -> str | None:
    """Open macOS Finder folder picker. Returns None when cancelled."""
    prompt = _escape_applescript_string(title)
    script = f'POSIX path of (choose folder with prompt "{prompt}"'
    if default_path and default_path.strip():
        location = _escape_applescript_string(default_path.strip())
        script += f' default location (POSIX file "{location}")'
    script += ")"
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        env=subprocess_env(),
    )
    if result.returncode != 0:
        return None
    path = result.stdout.strip()
    return path or None


def pick_folder_native(
    *,
    default_path: str | None = None,
    title: str = "작업 폴더 선택",
) -> tuple[bool, str | None]:
    """Return (available, path). path is None when cancelled or unavailable."""
    if platform.system() != "Darwin":
        return False, None
    return True, pick_folder_macos(default_path=default_path, title=title)
