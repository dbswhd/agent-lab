"""Room task list and chat visibility (Phase 1)."""

from __future__ import annotations

import pytest

from agent_lab.room import ChatMessage, _append_peer_turn_digest
from agent_lab.room_chat_channels import message_visibility
from agent_lab.room_tasks import (
    add_task,
    assign_tasks_to_agents,
    auto_claim_tasks_from_turn,
    build_team_task_block,
    claim_task,
    claimable_tasks,
    complete_task,
    complete_tasks_for_execution,
    consensus_tasks_ready,
    extract_proposed_titles,
    harvest_task_endorsements,
    list_tasks,
    set_team_lead_agent,
    sync_tasks_after_turn,
    sync_tasks_from_messages,
    sync_tasks_plan_links,
    tasks_public_payload,
    write_tasks,
)


class _Msg:
    def __init__(self, role: str, content: str, **kwargs):
        self.role = role
        self.content = content
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_extract_proposed_titles():
    text = "See [PROPOSED: Value-Up Overlay V0] and [PROPOSED: risk check]."
    titles = extract_proposed_titles(text)
    assert "Value-Up Overlay V0" in titles
    assert len(titles) == 2


def test_task_claim_and_complete():
    run_meta: dict = {"tasks": []}
    t = add_task(run_meta, "Wire kr_vu_overlay tab", source="test")
    assert t["status"] == "pending"
    claimed = claim_task(run_meta, t["id"], "cursor")
    assert claimed["status"] == "in_progress"
    assert claimed["owner_agent"] == "cursor"
    done = complete_task(run_meta, t["id"], artifact_refs=["plan.md#L10"])
    assert done["status"] == "completed"
    assert "plan.md#L10" in done["artifact_refs"]


def test_sync_tasks_from_messages_dedupes():
    run_meta: dict = {"tasks": []}
    msgs = [
        _Msg("user", "go"),
        _Msg(
            "agent",
            "[PROPOSED: Same idea] details",
            agent="codex",
            parallel_round=1,
        ),
        _Msg(
            "agent",
            "more [PROPOSED: Same idea]",
            agent="claude",
            parallel_round=1,
        ),
    ]
    created = sync_tasks_from_messages(run_meta, msgs, human_turn=1)
    assert len(created) == 1
    assert list_tasks(run_meta)[0]["title"] == "Same idea"


def test_sync_tasks_after_turn_sets_lead():
    run_meta: dict = {}
    sync_tasks_after_turn(run_meta, [], human_turn=1)
    assert run_meta.get("team_lead") == "cursor"


def test_message_visibility_peer_echo():
    vis = message_visibility(
        role="agent",
        content="[이번 턴 · 동료 발화] Codex said …",
    )
    assert vis == "peer"


def test_strip_peer_header_echo_keeps_real_content_human_visible():
    from agent_lab.room_chat_channels import strip_peer_header_echo

    # Real reply that merely *prepends* the echoed header must stay visible.
    body = "[이번 턴 · 동료 발화] Claude TS 선택에 동의합니다. 다음 수정은…"
    stripped = strip_peer_header_echo(body)
    assert stripped == "Claude TS 선택에 동의합니다. 다음 수정은…"
    assert message_visibility(role="agent", content=stripped) == "human"

    # No header → unchanged. Pure echo → kept (still hidden by visibility).
    assert strip_peer_header_echo("plain reply") == "plain reply"
    assert (
        message_visibility(
            role="agent",
            content=strip_peer_header_echo("[이번 턴 · 동료 발화]"),
        )
        == "peer"
    )


def test_append_peer_turn_digest_once():
    msgs = [
        ChatMessage(role="user", agent=None, content="topic"),
        ChatMessage(
            role="agent",
            agent="codex",
            content="first",
            parallel_round=1,
        ),
        ChatMessage(
            role="agent",
            agent="claude",
            content="second round",
            parallel_round=2,
        ),
    ]
    out = _append_peer_turn_digest(msgs)
    assert len(out) == len(msgs) + 1
    assert out[-1].visibility == "peer"
    again = _append_peer_turn_digest(out)
    assert len(again) == len(out)


def test_claimable_respects_dependencies():
    run_meta: dict = {"tasks": []}
    a = add_task(run_meta, "step A", source="test")
    b = add_task(run_meta, "step B", source="test", depends_on=[a["id"]])
    assert len(claimable_tasks(list_tasks(run_meta))) == 1
    claim_task(run_meta, a["id"], "codex")
    complete_task(run_meta, a["id"])
    assert len(claimable_tasks(list_tasks(run_meta))) == 1
    claimable = claimable_tasks(list_tasks(run_meta))
    assert claimable[0]["id"] == b["id"]


def test_tasks_public_payload():
    run_meta: dict = {"tasks": [], "team_lead": "cursor", "turn_leads": {"1": "codex"}}
    add_task(run_meta, "t1", source="test")
    payload = tasks_public_payload(run_meta)
    assert payload["counts"]["pending"] == 1
    assert payload["team_lead"] == "cursor"
    assert payload["turn_leads"]["1"] == "codex"


def test_assign_tasks_round_robin_skips_lead():
    run_meta: dict = {"tasks": [], "team_lead": "cursor"}
    for title in ("A", "B", "C"):
        add_task(run_meta, title, source="test")
    assigned = assign_tasks_to_agents(run_meta, ["cursor", "codex", "claude"], max_per_agent=2)
    assert len(assigned) == 3
    owners = [t["owner_agent"] for t in list_tasks(run_meta) if t.get("owner_agent")]
    assert "cursor" not in owners
    assert set(owners) == {"codex", "claude"}
    assert owners.count("codex") >= 1
    assert owners.count("claude") >= 1


def test_build_team_task_block_lead_vs_teammate():
    run_meta: dict = {"team_lead": "cursor", "tasks": []}
    t = add_task(run_meta, "Ship overlay", source="test")
    claim_task(run_meta, t["id"], "codex")
    lead_block = build_team_task_block(run_meta, "cursor")
    assert "팀 리드" in lead_block
    assert "Ship overlay" in lead_block
    assert "@codex" in lead_block
    assert build_team_task_block(run_meta, "claude") == ""
    add_task(run_meta, "Unassigned task", source="test")
    mate_block2 = build_team_task_block(run_meta, "claude")
    assert "청구 가능" in mate_block2
    assert "Unassigned task" in mate_block2


def test_set_team_lead_agent():
    run_meta: dict = {}
    assert set_team_lead_agent(run_meta, "codex") == "codex"
    assert run_meta["team_lead"] == "codex"


def test_sync_tasks_plan_links():
    run_meta: dict = {"tasks": []}
    add_task(run_meta, "Add smoke test for room tasks", source="test")
    plan = """## 지금 실행
1.
   - 무엇을: Add smoke test for room tasks
   - 어디서: tests/
   - 검증: pytest
"""
    assert sync_tasks_plan_links(run_meta, plan) == 1
    t = list_tasks(run_meta)[0]
    assert t.get("plan_action_index") == 1


def test_harvest_task_endorsements_and_consensus_gate():
    run_meta: dict = {"tasks": [], "agents": ["cursor", "codex", "claude"]}
    task = add_task(run_meta, "Ship feature", source="test")
    tid = task["id"]
    msgs = [
        _Msg(
            "agent",
            "ok",
            agent="codex",
            envelope={"act": "ENDORSE", "refs": [tid]},
        ),
    ]
    harvest_task_endorsements(run_meta, msgs, ["codex", "claude", "cursor"])
    ready, blockers = consensus_tasks_ready(run_meta, ["cursor", "codex", "claude"])
    assert not ready
    assert blockers
    msgs.append(
        _Msg(
            "agent",
            "ok",
            agent="claude",
            envelope={"act": "ENDORSE", "refs": [tid]},
        ),
    )
    harvest_task_endorsements(run_meta, msgs, ["codex", "claude", "cursor"])
    ready2, _ = consensus_tasks_ready(run_meta, ["cursor", "codex", "claude"])
    assert ready2


def test_tasks_public_payload_includes_consensus_gate():
    from agent_lab.room_tasks import add_task, tasks_public_payload

    run_meta: dict = {"tasks": [], "agents": ["cursor", "codex", "claude"]}
    add_task(run_meta, "Next check", source="test")
    payload = tasks_public_payload(run_meta)
    gate = payload.get("consensus_gate") or {}
    assert gate.get("required_endorsements") == 2
    assert gate.get("active_agent_count") == 3
    blocked = gate.get("blocked_tasks") or []
    assert len(blocked) == 1
    assert blocked[0].get("title") == "Next check"
    assert blocked[0].get("endorsements") == 0


def test_complete_tasks_for_execution():
    run_meta: dict = {"tasks": []}
    add_task(run_meta, "Edit file", source="test")
    tasks = list_tasks(run_meta)
    tasks[0]["plan_action_index"] = 2
    tasks[0]["plan_action_id"] = "plan-action-now-2"
    write_tasks(run_meta, tasks)
    done = complete_tasks_for_execution(
        run_meta,
        action_index=2,
        execution_id="exec-abc",
        execution={"status": "completed", "action_index": 2},
    )
    assert len(done) == 1
    assert done[0]["status"] == "completed"
    assert any("exec-abc" in r for r in done[0].get("artifact_refs") or [])


def test_complete_tasks_skipped_when_execution_review_required():
    run_meta: dict = {"tasks": []}
    add_task(run_meta, "PDF gate", source="test")
    tasks = list_tasks(run_meta)
    tasks[0]["plan_action_index"] = 1
    write_tasks(run_meta, tasks)
    done = complete_tasks_for_execution(
        run_meta,
        action_index=1,
        execution_id="exec-r1",
        execution={"status": "review_required", "action_index": 1},
    )
    assert done == []
    assert list_tasks(run_meta)[0]["status"] == "pending"


def test_sync_tasks_after_turn_skips_plan_links_on_discuss():
    run_meta: dict = {"tasks": [], "turn_state": {"open_issues": ["from state"]}}
    add_task(run_meta, "Match plan action title here", source="test")
    plan = """## 지금 실행
1.
   - 무엇을: Match plan action title here
   - 어디서: tests/
   - 검증: ok
"""
    out = sync_tasks_after_turn(
        run_meta,
        [],
        human_turn=1,
        plan_md=plan,
        mode="discuss",
        synthesize=False,
        consensus_mode=False,
    )
    assert out["discuss_only"] is True
    assert out["plan_links"] == 0
    assert list_tasks(run_meta)[0].get("plan_action_index") is None


def test_auto_claim_from_envelope_refs():
    run_meta: dict = {"tasks": [], "team_lead": "cursor"}
    t = add_task(run_meta, "Overlay wiring", source="test")
    msgs = [
        _Msg("user", "go"),
        _Msg(
            "agent",
            "claiming",
            agent="codex",
            envelope={"act": "AMEND", "refs": [t["id"]]},
        ),
    ]
    claimed = auto_claim_tasks_from_turn(run_meta, msgs, lead_agent="cursor")
    assert len(claimed) == 1
    assert list_tasks(run_meta)[0]["owner_agent"] == "codex"


def test_complete_task_blocked_on_artifact_execution_ref():
    run_meta: dict = {
        "tasks": [],
        "executions": [
            {
                "id": "exec-art",
                "status": "review_required",
                "action_index": 1,
            }
        ],
    }
    task = add_task(run_meta, "Verify", source="test")
    tasks = list_tasks(run_meta)
    tasks[0]["artifact_refs"] = ["execution:exec-art"]
    write_tasks(run_meta, tasks)
    with pytest.raises(ValueError, match="검증"):
        complete_task(run_meta, task["id"])


def test_complete_task_blocked_on_review_required_execution():
    run_meta: dict = {
        "tasks": [],
        "executions": [
            {
                "id": "exec-1",
                "action_index": 3,
                "action_id": "plan-action-now-3",
                "status": "review_required",
            }
        ],
    }
    task = add_task(run_meta, "Verify PDF", source="test")
    tasks = list_tasks(run_meta)
    tasks[0]["plan_action_index"] = 3
    tasks[0]["plan_action_id"] = "plan-action-now-3"
    write_tasks(run_meta, tasks)
    with pytest.raises(ValueError, match="검증"):
        complete_task(run_meta, task["id"])
