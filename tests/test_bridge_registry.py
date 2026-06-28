"""Bridge registry + check_bridge_processes tests (M4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def bridge_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg = tmp_path / ".agent-lab"
    cfg.mkdir()
    monkeypatch.setattr("agent_lab.app_config.config_dir", lambda: cfg)
    return cfg


def test_register_and_audit_round_trip(bridge_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.cursor.registry import audit_bridge_processes, load_records, register_bridge

    monkeypatch.setattr(
        "agent_lab.cursor.registry.list_live_bridge_processes",
        lambda: [{"pid": 4242, "command": "cursor-sdk-bridge", "alive": True}],
    )
    monkeypatch.setattr("agent_lab.cursor.registry._pid_alive", lambda pid: pid == 4242)

    register_bridge("/tmp/ws", pid=4242, mode="auto")
    audit = audit_bridge_processes(stale_after_hours=9999)
    assert audit["record_count"] == 1
    assert audit["stale_count"] == 0
    assert load_records()[0].workspace.endswith("/tmp/ws")


def test_cleanup_prunes_stale_registry_rows(bridge_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.cursor import registry as br

    br.save_records(
        [
            br.BridgeRecord(workspace="/old", pid=1, last_seen_at="2000-01-01T00:00:00+00:00"),
            br.BridgeRecord(workspace="/active", pid=99, last_seen_at=br._now_iso()),
        ]
    )
    monkeypatch.setattr(br, "_pid_alive", lambda pid: pid == 99)
    monkeypatch.setattr(br, "list_live_bridge_processes", lambda: [])

    result = br.cleanup_stale_bridges(prune_registry=True, kill_orphans=False)
    assert result["removed_registry"] == 1
    kept = br.load_records()
    assert len(kept) == 1
    assert kept[0].workspace.endswith("/active")


def test_check_bridge_processes_script_json() -> None:
    import subprocess
    import sys

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_bridge_processes.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--json"],
        cwd=script.parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["action"] == "audit"
    assert "audit" in payload
