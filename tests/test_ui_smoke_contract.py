"""P0 UI smoke fixture and Makefile wiring."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "sessions" / "_regression" / "ui_pending_diff"


def _load_validator():
    path = ROOT / "scripts" / "verify_ui_smoke_fixture.py"
    spec = importlib.util.spec_from_file_location("verify_ui_smoke_fixture", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_dry_run(target: str) -> str:
    env = os.environ.copy()
    for key in ("MAKEFLAGS", "MFLAGS", "MAKELEVEL"):
        env.pop(key, None)
    result = subprocess.run(
        ["make", "-n", target],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_ui_pending_diff_fixture_contract():
    validator = _load_validator()

    assert validator.validate_fixture(fixture=FIXTURE) == []


def test_ui_pending_diff_fixture_is_read_only_pending_state():
    run = json.loads((FIXTURE / "run.json").read_text(encoding="utf-8"))
    pending = [row for row in run["executions"] if row.get("status") == "pending_approval"]

    assert len(pending) == 1
    assert pending[0]["isolation_effective"] == "snapshot_override"
    assert "P0_UI_DIFF_MARKER" in pending[0]["diff"]


def test_ui_smoke_make_targets_are_separate():
    web = _make_dry_run("smoke-web-ui")
    tauri = _make_dry_run("smoke-tauri-ui")

    assert "scripts/smoke_web_ui.sh" in web
    assert "scripts/smoke_tauri_ui.sh" not in web
    assert "scripts/smoke_tauri_ui.sh" in tauri
    assert "scripts/smoke_web_ui.sh" not in tauri


def test_web_smoke_has_repo_local_playwright_dependency():
    package = json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))

    assert "playwright" in package["devDependencies"]
