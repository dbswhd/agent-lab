"""GUI-style minimal PATH: codex + cursor bridge resolve after configure."""

from __future__ import annotations

import glob
import os
import subprocess
from pathlib import Path

import pytest


def _codex_installed() -> bool:
    import shutil

    if shutil.which("codex"):
        return True
    home = Path.home()
    for p in glob.glob(str(home / ".nvm/versions/node/*/bin/codex")):
        if Path(p).is_file():
            return True
    for candidate in (
        home / ".local/bin/codex",
        Path("/opt/homebrew/bin/codex"),
        Path("/usr/local/bin/codex"),
    ):
        if candidate.is_file():
            return True
    return False


def test_configure_subprocess_path_enables_codex(monkeypatch):
    if not _codex_installed():
        pytest.skip("codex not installed in this environment")

    monkeypatch.chdir("/")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.delenv("CODEX_BIN", raising=False)
    monkeypatch.delenv("CURSOR_SDK_BRIDGE_BIN", raising=False)

    from agent_lab.runtime_paths import configure_subprocess_path

    configure_subprocess_path()

    codex = os.environ.get("CODEX_BIN")
    assert codex, "expected CODEX_BIN after configure"
    proc = subprocess.run(
        [codex, "--version"],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout

    bridge = os.environ.get("CURSOR_SDK_BRIDGE_BIN")
    assert bridge and os.path.isfile(bridge)
