"""Regression tests for Hook · Communicate reform patches."""

from __future__ import annotations

from agent_lab.room import _delegate_run_meta_patch
from agent_lab.room.consensus import ConsensusAnchor, consensus_follow_up
from agent_lab.run.meta import append_hook_run, read_run_meta
from agent_lab.session.guidance import preserve_session_meta_from_prev


def test_consensus_follow_up_omits_envelope_protocol():
    anchor = ConsensusAnchor(agent="codex", excerpt="ship feature X", parallel_round=1)
    block = consensus_follow_up(anchor)
    assert "```agent-envelope" not in block
    assert "합의 확인" in block
    assert "ship feature X" in block


def test_hook_runs_preserved_via_session_meta_keys(tmp_path):
    append_hook_run(
        tmp_path,
        {
            "event": "pre_agent_reply",
            "agent": "cursor",
            "exit_code": 0,
            "sub_reason": "",
            "blocked": False,
        },
    )
    prev = read_run_meta(tmp_path)
    run_meta: dict = {}
    preserve_session_meta_from_prev(run_meta, prev)
    assert len(run_meta.get("hook_runs") or []) == 1
    assert run_meta["hook_runs"][0]["agent"] == "cursor"


def test_delegate_run_meta_patch_includes_hook_runs():
    patch = _delegate_run_meta_patch(
        {
            "hook_runs": [{"event": "post_harvest", "exit_code": 0}],
        }
    )
    assert patch is not None
    assert len(patch["hook_runs"]) == 1
