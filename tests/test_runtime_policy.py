from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.run_meta import patch_run_meta
from agent_lab.runtime.policy import PolicyEngine
from agent_lab.room_hooks import PreExecuteBlocked


@pytest.fixture
def session_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "sess-policy"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    return folder


def test_gate_snapshot_empty_run() -> None:
    snap = PolicyEngine.gate_snapshot({})
    assert snap["next_allowed_action"] == "discuss"
    assert snap.get("block_source") is None


def test_execute_block_reason_from_objection(session_folder: Path) -> None:
    def _block(run: dict) -> dict:
        run["objections"] = [
            {
                "id": "obj-1",
                "act": "BLOCK",
                "status": "open",
                "body": "stop execute",
            }
        ]
        return run

    patch_run_meta(session_folder, _block)
    from agent_lab.run_meta import read_run_meta

    reason = PolicyEngine.execute_block_reason(read_run_meta(session_folder))
    assert reason is not None
    assert "stop" in reason.lower() or "obj" in reason.lower()


def test_pre_execute_hook_blocks(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab import room_hooks

    def _fake_pre_execute(*_a, **_k):
        from agent_lab.room_hooks import HookResult

        return HookResult(
            blocked=True,
            feedback="policy test block",
            exit_code=2,
            event="pre_execute",
        )

    monkeypatch.setattr(room_hooks, "run_hook", _fake_pre_execute)
    from agent_lab.run_meta import read_run_meta

    run = read_run_meta(session_folder)
    with pytest.raises(PreExecuteBlocked, match="policy test block"):
        PolicyEngine.require_pre_execute(
            run,
            {"index": 1, "what": "x", "where": "y", "verify": "z"},
            session_folder=session_folder,
            session_id=session_folder.name,
        )


def test_format_gate_block_when_blocked() -> None:
    snap = {
        "block_source": "open_objection",
        "block_reason": "BLOCK on task",
        "next_allowed_action": "blocked",
        "gates": {"inbox": {"pending": 0}, "execute": {"open": False}},
    }
    block = PolicyEngine.format_gate_block(snap)
    assert "[Gate snapshot]" in block
    assert "open_objection" in block
