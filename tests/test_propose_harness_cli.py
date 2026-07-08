"""HS3-5 — scripts/propose_harness.py CLI smoke tests (mock-only, subprocess)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "propose_harness.py"


def _run(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    import os

    full_env = {**os.environ, "AGENT_LAB_RUN_PROFILE": "balanced"}
    full_env.pop("AGENT_LAB_MOCK_AGENTS", None)
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=full_env,
    )


def test_list_mode_exits_zero(tmp_path):
    proc = _run(["--mode", "list", "--root", str(tmp_path)])
    assert proc.returncode == 0
    assert "STOP guard" in proc.stdout


def test_propose_mode_writes_candidate(tmp_path):
    proc = _run(
        [
            "--mode",
            "propose",
            "--root",
            str(tmp_path),
            "--pattern-id",
            "fp:weak_taste:standard",
            "--axis",
            "profile",
            "--files",
            "src/agent_lab/run/profile.py",
            "--diff-ref",
            "manual-review",
        ]
    )
    assert proc.returncode == 0, proc.stderr
    assert "proposed:" in proc.stdout

    candidates_dir = tmp_path / ".agent-lab" / "harness" / "candidates"
    written = list(candidates_dir.glob("*/candidate.json"))
    assert len(written) == 1
    data = json.loads(written[0].read_text(encoding="utf-8"))
    assert data["axis"] == "profile"
    assert data["tier"] == "A"


def test_propose_mode_rejected_exits_nonzero(tmp_path):
    proc = _run(
        [
            "--mode",
            "propose",
            "--root",
            str(tmp_path),
            "--pattern-id",
            "fp:x",
            "--axis",
            "profile",
            "--files",
            "src/agent_lab/human_inbox.py",
            "--diff-ref",
            "x",
        ]
    )
    assert proc.returncode == 1
    assert "REJECTED" in proc.stderr


def test_propose_mode_missing_required_args_exits_2(tmp_path):
    proc = _run(["--mode", "propose", "--root", str(tmp_path)])
    assert proc.returncode == 2


def test_propose_mode_stop_guard_blocks(tmp_path):
    proc = _run(
        [
            "--mode",
            "propose",
            "--root",
            str(tmp_path),
            "--pattern-id",
            "fp:x",
            "--axis",
            "profile",
            "--files",
            "src/agent_lab/run/profile.py",
            "--diff-ref",
            "x",
        ],
        env={"AGENT_LAB_MOCK_AGENTS": "1"},
    )
    assert proc.returncode == 1
    assert "STOP guard" in proc.stderr
