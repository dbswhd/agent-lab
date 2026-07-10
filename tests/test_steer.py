"""ABSORB P1 — Human steer queue (informational only)."""

from __future__ import annotations

from pathlib import Path

from agent_lab.run.meta import read_run_meta, write_run_meta
from agent_lab.steer import drain_steer_follow_up, enqueue_steer, list_steer_queue


def _session(tmp_path: Path) -> Path:
    folder = tmp_path / "sess_steer"
    folder.mkdir()
    write_run_meta(
        folder,
        {"_session_id": folder.name, "_session_folder": str(folder)},
    )
    return folder


def test_enqueue_and_drain_steer(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    result = enqueue_steer(folder, "focus on tests only")
    assert result["ok"] is True
    assert result["queued"] == 1
    meta = read_run_meta(folder)
    assert len(list_steer_queue(meta)) == 1

    block = drain_steer_follow_up(folder)
    assert "Human steer" in block
    assert "focus on tests only" in block
    assert list_steer_queue(read_run_meta(folder)) == []


def test_drain_respects_target(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    enqueue_steer(folder, "room only", target="room")
    enqueue_steer(folder, "execute only", target="execute")
    block = drain_steer_follow_up(folder, target="execute")
    assert "execute only" in block
    assert "room only" not in block
    remaining = list_steer_queue(read_run_meta(folder))
    assert len(remaining) == 1
    assert remaining[0]["text"] == "room only"


def test_enrich_execute_prompt_drains_steer(tmp_path: Path) -> None:
    from agent_lab.runtime.context import enrich_execute_prompt

    folder = _session(tmp_path)
    enqueue_steer(folder, "skip docs", target="execute")
    meta = read_run_meta(folder)
    out = enrich_execute_prompt("do the patch", meta, session_folder=folder)
    assert "skip docs" in out
    assert "do the patch" in out
    assert list_steer_queue(read_run_meta(folder)) == []
