"""RI-05 — independent divergence and stage-scoped roles on the idea lane."""

from __future__ import annotations

import pytest

from agent_lab import ideation
from agent_lab.agents.prompts import (
    IDEATION_EXPLORE_INSTRUCTION,
    IDEATION_PERSPECTIVES,
    IDEATION_SHAPE_INSTRUCTION,
    ideation_perspective_for_seat,
)
from agent_lab.reply_policy import envelope_follow_up_block, resolve_reply_policy
from agent_lab.role_plan import resolve_role_plan
from agent_lab.run.state import RunState


def _run(stage: str | None, **extra) -> RunState:
    run = RunState.from_memory({"topic": "막연한 개념", "agents": ["cursor", "codex", "claude"], **extra})
    if stage is not None:
        payload = ideation.new_ideation(original_concept="막연한 개념")
        payload["stage"] = stage
        ideation.start_ideation(run, payload)
    return run


# --- independent first batch --------------------------------------------


class _Recorder:
    """Captures the thread each seat was given, and fails one provider."""

    def __init__(self, fail: str | None = None) -> None:
        self.threads: dict[str, list] = {}
        self.fail = fail

    def __call__(self, agent, *, topic, thread, **kwargs):
        from agent_lab.room.messages import ChatMessage

        self.threads[str(agent)] = list(thread)
        if self.fail and str(agent) == self.fail:
            # Mirrors the real contract: `_call_one_agent` turns a provider
            # failure into a visible system message rather than raising.
            return ChatMessage(role="system", agent=str(agent), content=f"[{agent} error] provider is down")
        return ChatMessage(role="assistant", agent=str(agent), content=f"{agent}의 구상")


@pytest.fixture()
def recorder(monkeypatch):
    from agent_lab.room import parallel_rounds

    rec = _Recorder()
    monkeypatch.setattr(parallel_rounds, "_invoke_agent_for_round", rec)
    monkeypatch.setattr(parallel_rounds, "_teammate_idle_peer_message", lambda *a, **k: None)
    return rec


def _round(run, recorder, *, agents=("cursor", "codex", "claude"), parallel_round=1, task_type=None):
    from agent_lab.room.parallel_rounds import run_parallel_round

    return run_parallel_round(
        "막연한 개념",
        [],
        list(agents),
        parallel_round=parallel_round,
        run_meta=run,
        task_type=task_type,
    )


def test_first_batch_never_shows_a_peer_answer(recorder):
    replies = _round(_run(ideation.STAGE_EXPLORE), recorder)

    assert len(replies) == 3
    for agent, thread in recorder.threads.items():
        assert thread == [], f"{agent} saw a peer answer in its own batch: {thread}"


def test_first_batch_stays_parallel_even_for_a_sequential_task_type(recorder):
    """peer_review would normally force a sequential (peer-reading) round."""
    _round(_run(ideation.STAGE_EXPLORE), recorder, task_type="peer_review")
    assert all(thread == [] for thread in recorder.threads.values())


def test_lead_last_does_not_expose_the_batch_while_exploring(recorder, monkeypatch):
    from agent_lab.room import team_orchestration

    monkeypatch.setattr(team_orchestration, "lead_last_r1_enabled", lambda run_meta: True)
    run = _run(ideation.STAGE_EXPLORE, team_lead="claude")
    _round(run, recorder)
    assert all(thread == [] for thread in recorder.threads.values())


def test_later_rounds_still_build_on_peers(recorder):
    """Comparison and synthesis happen after the batch, not inside it."""
    _round(_run(ideation.STAGE_EXPLORE), recorder, parallel_round=2)
    threads = [recorder.threads[a] for a in ("cursor", "codex", "claude")]
    assert threads[0] == []
    assert len(threads[-1]) > 0


def test_shaping_is_not_forced_independent(recorder):
    _round(_run(ideation.STAGE_SHAPE), recorder, parallel_round=2)
    assert len(recorder.threads["claude"]) > 0


def test_one_provider_failure_keeps_the_other_candidates(monkeypatch):
    """Partial candidates survive, and the failure is shown rather than hidden."""
    from agent_lab.room import parallel_rounds

    rec = _Recorder(fail="codex")
    monkeypatch.setattr(parallel_rounds, "_invoke_agent_for_round", rec)
    monkeypatch.setattr(parallel_rounds, "_teammate_idle_peer_message", lambda *a, **k: None)

    replies = _round(_run(ideation.STAGE_EXPLORE), rec)
    by_agent = {m.agent: m for m in replies}
    assert set(by_agent) == {"cursor", "codex", "claude"}
    assert by_agent["cursor"].role == "assistant"
    assert by_agent["claude"].role == "assistant"
    assert by_agent["codex"].role == "system"
    assert "error" in by_agent["codex"].content


def test_a_single_model_roster_still_explores(recorder):
    replies = _round(_run(ideation.STAGE_EXPLORE), recorder, agents=("cursor",))
    assert len(replies) == 1
    assert recorder.threads["cursor"] == []


def test_existing_sessions_are_unaffected(recorder, monkeypatch):
    from agent_lab.room import team_orchestration

    monkeypatch.setattr(team_orchestration, "lead_last_r1_enabled", lambda run_meta: True)
    _round(_run(None, team_lead="claude"), recorder)
    # lead-last is still in play: the lead reads the parallel batch
    assert len(recorder.threads["claude"]) > 0


# --- stage-scoped roles --------------------------------------------------


class _Route:
    category = "deep"
    task_type = "general"


AGENTS = ["cursor", "codex", "claude"]


def test_exploration_drops_provider_pinned_roles():
    """`claude`=synthesizer / `codex`=critic would fight divergence (§4.3)."""
    assert resolve_role_plan(route=_Route(), agents=AGENTS, run_meta=_run(ideation.STAGE_EXPLORE)) == {}


@pytest.mark.parametrize("stage", [ideation.STAGE_SHAPE, ideation.STAGE_PLAN])
def test_roles_return_after_a_direction_is_chosen(stage):
    """Feasibility criticism belongs after the selection, not during it."""
    assert resolve_role_plan(route=_Route(), agents=AGENTS, run_meta=_run(stage)) != {}


def test_roles_unchanged_for_existing_sessions():
    baseline = resolve_role_plan(route=_Route(), agents=AGENTS)
    assert baseline == resolve_role_plan(route=_Route(), agents=AGENTS, run_meta=_run(None))
    assert baseline != {}


def test_perspectives_are_seat_keyed_not_provider_keyed():
    seats = [ideation_perspective_for_seat(i) for i in range(len(IDEATION_PERSPECTIVES))]
    assert len(set(seats)) == len(IDEATION_PERSPECTIVES)
    assert ideation_perspective_for_seat(0) == ideation_perspective_for_seat(len(IDEATION_PERSPECTIVES))
    assert ideation_perspective_for_seat(0)


# --- conflicting guidance ------------------------------------------------


def test_consensus_envelope_is_suppressed_while_exploring():
    policy = resolve_reply_policy(parallel_round=2, consensus_mode=True, ideation_stage=ideation.STAGE_EXPLORE)
    assert policy.inject_envelope_guidance is False
    assert policy.envelope_strict is False
    assert policy.inject_decision_fork is False
    assert policy.inject_coordination is False
    assert envelope_follow_up_block(policy, context="consensus") == ""


@pytest.mark.parametrize("stage", [None, ideation.STAGE_SHAPE, ideation.STAGE_PLAN])
def test_envelope_guidance_is_unchanged_elsewhere(stage):
    baseline = resolve_reply_policy(parallel_round=2, consensus_mode=True)
    policy = resolve_reply_policy(parallel_round=2, consensus_mode=True, ideation_stage=stage)
    assert policy == baseline
    assert policy.inject_envelope_guidance is True


def test_stage_instructions_do_not_ask_for_both_things_at_once():
    assert "envelope" in IDEATION_EXPLORE_INSTRUCTION
    assert "가정:" in IDEATION_EXPLORE_INSTRUCTION
    assert "기각한 후보" in IDEATION_SHAPE_INSTRUCTION
    assert IDEATION_EXPLORE_INSTRUCTION != IDEATION_SHAPE_INSTRUCTION


# --- conflicting fixed guidance (payload-level) --------------------------


def _payload(tmp_path, stage, agent="claude", parallel_round=2):
    from agent_lab.room.parallel_rounds import preview_agent_payload
    from agent_lab.run.meta import write_run_meta

    folder = tmp_path / f"sess-{stage}-{agent}-{parallel_round}"
    folder.mkdir()
    (folder / "topic.txt").write_text("막연한 개념\n", encoding="utf-8")
    run = _run(stage, consensus_mode=True, _active_consensus=True)
    write_run_meta(folder, dict(run))
    text, _ = preview_agent_payload(folder, agent, agents=["cursor", "codex", "claude"], parallel_round=parallel_round)
    return text


def test_exploration_payload_carries_no_instruction_to_use_the_envelope(tmp_path):
    """Captured payload check — the plan's manual step, pinned as a test."""
    text = _payload(tmp_path, ideation.STAGE_EXPLORE)
    assert "[PLATFORM.md" not in text
    assert "[아이디어 Room 프로토콜]" in text
    assert IDEATION_EXPLORE_INSTRUCTION in text
    # every remaining mention must be a prohibition, not an instruction
    for line in text.splitlines():
        if "ENDORSE" in line or "CHALLENGE" in line:
            assert "쓰지" in line or "않" in line, f"conflicting envelope instruction survived: {line}"


def test_exploration_payload_drops_peer_reaction_guidance(tmp_path):
    text = _payload(tmp_path, ideation.STAGE_EXPLORE)
    assert "[Conversation guidance — 구상 탐색]" in text
    assert "three parallel essays" not in text
    assert "[Multi-agent coordination" not in text


def test_existing_session_payload_is_unchanged(tmp_path):
    text = _payload(tmp_path, None)
    assert "[PLATFORM.md" in text
    assert "[아이디어 Room 프로토콜]" not in text
    assert "three parallel essays" in text


def test_shaping_payload_keeps_the_platform_protocol(tmp_path):
    text = _payload(tmp_path, ideation.STAGE_SHAPE)
    assert "[PLATFORM.md" in text
    assert IDEATION_SHAPE_INSTRUCTION in text


def test_system_prompt_override_only_on_exploration():
    from agent_lab.agents.prompts import CLAUDE_ROOM, ideation_system_prompt

    system = ideation_system_prompt("claude")
    assert CLAUDE_ROOM.rstrip() in system, "the provider runtime identity must survive"
    assert "고정 역할" in system
    assert ideation_system_prompt("unknown-agent") == ""
