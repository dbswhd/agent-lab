"""Sprint C — turn lead, R1 order, discuss assign policy, human synthesis."""

from __future__ import annotations

from agent_lab.room import ChatMessage, _append_human_turn_synthesis, _round_agent_order
from agent_lab.room_team_orchestration import (
    build_human_turn_synthesis,
    is_discuss_only_turn,
    parse_go_lead_from_message,
    resolve_send_receipt,
    resolve_turn_lead,
    should_assign_tasks_on_turn,
    should_emit_human_turn_synthesis,
    team_r1_split,
    turn_leads_map,
)


def test_parse_go_lead_from_message():
    assert parse_go_lead_from_message("GO codex\nplease review") == "codex"
    assert parse_go_lead_from_message("리드: claude") == "claude"
    assert parse_go_lead_from_message("hello") is None


def test_resolve_turn_lead_explicit_and_rotate():
    meta: dict = {"team_lead": "cursor"}
    agents = ["cursor", "codex", "claude"]
    assert resolve_turn_lead(meta, 1, agents, user_message="GO codex") == "codex"
    assert turn_leads_map(meta)["1"] == "codex"
    assert resolve_turn_lead(meta, 2, agents) == "codex"
    assert turn_leads_map(meta)["2"] == "codex"
    assert resolve_turn_lead(meta, 3, agents) == "claude"


def test_resolve_send_receipt():
    assert (
        resolve_send_receipt(
            mode="discuss",
            synthesize=False,
            consensus_mode=False,
        )
        == "discuss_saved"
    )
    assert (
        resolve_send_receipt(
            mode="plan",
            synthesize=True,
            consensus_mode=False,
            plan_updated=True,
        )
        == "plan_updated"
    )
    assert (
        resolve_send_receipt(
            mode="discuss",
            synthesize=False,
            consensus_mode=True,
            consensus={"status": "reached"},
        )
        == "consensus_done"
    )
    assert (
        resolve_send_receipt(
            mode="plan",
            synthesize=True,
            consensus_mode=False,
            plan_workflow_phase="PEER_REVIEW",
        )
        == "plan_peer_review"
    )
    assert (
        resolve_send_receipt(
            mode="discuss",
            synthesize=False,
            consensus_mode=False,
            plan_workflow_phase="HUMAN_PENDING",
        )
        == "plan_pending_approval"
    )


def test_should_assign_tasks_on_turn():
    assert not should_assign_tasks_on_turn(mode="discuss", synthesize=False, consensus_mode=False)
    assert should_assign_tasks_on_turn(mode="discuss", synthesize=True, consensus_mode=False)
    assert should_assign_tasks_on_turn(mode="discuss", synthesize=False, consensus_mode=True)
    assert is_discuss_only_turn(mode="discuss", synthesize=False, consensus_mode=False)


def test_team_r1_split_lead_last():
    meta = {"team_lead": "cursor"}
    teammates, lead_tail = team_r1_split(["cursor", "codex", "claude"], meta)
    assert lead_tail == ["cursor"]
    assert set(teammates) == {"codex", "claude"}


def test_round_agent_order_r1_lead_last():
    meta = {"team_lead": "cursor"}
    order = _round_agent_order(
        ["cursor", "codex", "claude"],
        review_mode=False,
        parallel_round=1,
        run_meta=meta,
    )
    assert [str(a) for a in order] == ["codex", "claude", "cursor"]


def test_build_human_turn_synthesis_skips_peer():
    msgs = [
        ChatMessage(role="user", agent=None, content="topic?"),
        ChatMessage(
            role="agent",
            agent="codex",
            content="peer note",
            visibility="peer",
        ),
        ChatMessage(
            role="agent",
            agent="claude",
            content="Human-visible answer",
            visibility="human",
        ),
    ]
    body = build_human_turn_synthesis(msgs, lead="cursor", human_excerpt="topic?")
    assert "[human synthesis" in body
    assert "peer note" not in body
    assert "Human-visible answer" in body


def test_should_emit_human_turn_synthesis_profiles():
    msgs = [
        ChatMessage(role="user", agent=None, content="q"),
        ChatMessage(role="agent", agent="codex", content="a"),
        ChatMessage(role="agent", agent="claude", content="b"),
    ]
    assert not should_emit_human_turn_synthesis("analyze", msgs, agents_used=["codex", "claude"])
    assert should_emit_human_turn_synthesis(
        "analyze",
        msgs + [ChatMessage(role="agent", agent="cursor", content="c")],
        agents_used=["codex", "claude", "cursor"],
    )
    assert should_emit_human_turn_synthesis("free", msgs, agents_used=["codex"])
    assert not should_emit_human_turn_synthesis("quick", msgs, agents_used=["codex", "claude", "cursor"])


def test_append_human_turn_synthesis_once():
    msgs = [
        ChatMessage(role="user", agent=None, content="hello"),
        ChatMessage(role="agent", agent="codex", content="reply"),
    ]
    meta = {"team_lead": "cursor", "turn_profile": "free"}
    out = _append_human_turn_synthesis(msgs, meta, turn_meta={"turn_profile": "free", "agents": ["codex"]})
    assert len(out) == len(msgs) + 1
    assert "[human synthesis" in out[-1].content
    again = _append_human_turn_synthesis(out, meta, turn_meta={"turn_profile": "free", "agents": ["codex"]})
    assert len(again) == len(out)


def test_append_human_turn_synthesis_skipped_for_small_analyze():
    msgs = [
        ChatMessage(role="user", agent=None, content="hello"),
        ChatMessage(role="agent", agent="codex", content="reply"),
    ]
    out = _append_human_turn_synthesis(
        msgs,
        {"team_lead": "cursor", "turn_profile": "analyze"},
        turn_meta={"turn_profile": "analyze", "agents": ["codex"]},
    )
    assert len(out) == len(msgs)
