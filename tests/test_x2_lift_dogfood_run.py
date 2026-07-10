from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from scripts.x2_lift_dogfood_run import run_x2_lift_mock


def test_run_x2_lift_mock_uses_isolated_config_dir(monkeypatch, tmp_path: Path) -> None:
    outer_cfg = tmp_path / "outer-config"
    outer_cfg.mkdir()
    monkeypatch.setenv("AGENT_LAB_CONFIG_DIR", str(outer_cfg))
    env = dict(os.environ)
    env["AGENT_LAB_CONFIG_DIR"] = str(outer_cfg)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import sys,time; "
                "sys.path.insert(0, 'src'); "
                "from agent_lab.run.control import try_begin_run; "
                "assert try_begin_run(session_id='outer-lock', run_kind='room', label='Outer lock'); "
                "time.sleep(10)"
            ),
        ],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
    )
    try:
        report = run_x2_lift_mock(sessions_base=tmp_path / "sessions")
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    assert report["ok"] is True
    assert report["oracle_verdict"] == "pass"
    assert report["execution_status"] == "completed"
