"""Gate snapshot pure computation."""

from __future__ import annotations

from agent_lab.gate_snapshot import compute_gate_snapshot, format_gate_snapshot_block


def test_inbox_pending_blocks():
    meta = {
        "human_inbox": [{"id": "q1", "status": "pending", "prompt": "Pick A or B"}],
        "inbox_pending": True,
    }
    snap = compute_gate_snapshot(meta)
    assert snap["block_source"] == "inbox_pending"
    assert snap["next_allowed_action"] == "wait_human"
    block = format_gate_snapshot_block(snap)
    assert "inbox_pending" in block


def test_pre_execute_blocked():
    meta = {
        "executions": [
            {"pre_verify": {"blocked": True, "feedback": "lint failed"}},
        ],
    }
    snap = compute_gate_snapshot(meta)
    assert snap["block_source"] == "pre_execute"
    assert snap["gates"]["execute"]["open"] is False


def test_no_blockers():
    snap = compute_gate_snapshot({})
    assert snap["block_source"] is None
    assert format_gate_snapshot_block(snap) == ""
