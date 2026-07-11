from __future__ import annotations

from agent_lab.consensus_gate import consensus_action_block_reason


def _run() -> dict[str, object]:
    return {
        "consensus_mode": True,
        "agents": ["cursor", "codex"],
        "consensus": {
            "status": "reached",
            "anchor": {"id": "a1", "agent": "cursor", "excerpt": "use the parser"},
            "agents_consented": ["codex"],
            "endorse_count": 1,
        },
    }


def test_consensus_completeness_accepts_reached_consensus() -> None:
    assert consensus_action_block_reason(_run(), 1, "now") is None


def test_consensus_completeness_rejects_missing_anchor() -> None:
    run = _run()
    run["consensus"] = {"status": "reached", "agents_consented": ["codex"]}
    assert consensus_action_block_reason(run, 1, "now") == "consensus_anchor_incomplete"


def test_consensus_completeness_rejects_unreached_signal() -> None:
    run = _run()
    run["consensus"] = {"status": "open"}
    assert consensus_action_block_reason(run, 1, "now") == "consensus_not_reached"
