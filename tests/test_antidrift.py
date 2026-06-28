"""Anti-drift component A: state-externalization re-injection on panel turns (ultragoal G002).

Behind AGENT_LAB_ANTIDRIFT (default off). Panel turns (consensus_mode True) get a re-grounding
anchor that re-injects confirmed facts + the decision ledger; solo turns and the flag-off path
keep the plain confirmed-facts block (OFF-parity).
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_lab.context.bundle import (
    _format_clarity_facts,
    _format_decision_ledger,
    _format_grounding_block,
)
from agent_lab.turn_modes import antidrift_enabled

ANTI_DRIFT_HEADER = "anti-drift · 상태 재정렬"
LEDGER_HEADER = "[결정 로그]"


def _run_meta(*, facts: bool = True, ledger: bool = True) -> dict[str, Any]:
    run: dict[str, Any] = {}
    if facts:
        run["mission_loop"] = {
            "clarity": {
                "facts": [
                    {
                        "id": "q1",
                        "component": "auth",
                        "category": "scope",
                        "answer": "JWT only, no sessions",
                        "fact": "JWT only, no sessions",
                    }
                ]
            }
        }
    if ledger:
        run["goal_ledger"] = [
            {"at": "2026-06-22T00:00:00Z", "event": "mode_route", "phase": "DISCUSS"},
            {"at": "2026-06-22T00:01:00Z", "event": "plan_gate", "phase": "PLAN_GATE", "note": "draft approved"},
        ]
    return run


# --- AC6: OFF-parity — flag off => plain confirmed-facts block, byte-identical ---


@pytest.mark.parametrize("consensus_mode", [True, False])
def test_antidrift_off_is_plain_facts(consensus_mode: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_ANTIDRIFT", raising=False)
    run = _run_meta()
    grounding = _format_grounding_block(run, consensus_mode=consensus_mode)
    assert grounding == _format_clarity_facts(run)
    assert ANTI_DRIFT_HEADER not in grounding
    assert LEDGER_HEADER not in grounding


def test_antidrift_off_byte_identical_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_ANTIDRIFT", raising=False)
    run = _run_meta(facts=False, ledger=False)
    assert _format_grounding_block(run, consensus_mode=True) == _format_clarity_facts(run) == ""


# --- AC7: anti-drift panel re-injection (facts + ledger every panel turn) ---


def test_antidrift_on_panel_reinjects_facts_and_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ANTIDRIFT", "1")
    run = _run_meta()
    grounding = _format_grounding_block(run, consensus_mode=True)
    assert ANTI_DRIFT_HEADER in grounding
    assert "JWT only, no sessions" in grounding  # confirmed fact re-injected
    assert LEDGER_HEADER in grounding
    assert "plan_gate" in grounding
    assert "draft approved" in grounding


def test_antidrift_on_panel_without_ledger_still_reinjects_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ANTIDRIFT", "1")
    run = _run_meta(ledger=False)
    grounding = _format_grounding_block(run, consensus_mode=True)
    assert ANTI_DRIFT_HEADER in grounding
    assert "JWT only, no sessions" in grounding
    assert LEDGER_HEADER not in grounding


# --- AC7: solo turns stay light (plain facts), even with the flag on ---


def test_antidrift_on_solo_is_light(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ANTIDRIFT", "1")
    run = _run_meta()
    grounding = _format_grounding_block(run, consensus_mode=False)
    assert grounding == _format_clarity_facts(run)
    assert ANTI_DRIFT_HEADER not in grounding
    assert LEDGER_HEADER not in grounding


def test_antidrift_on_panel_empty_state_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ANTIDRIFT", "1")
    run = _run_meta(facts=False, ledger=False)
    assert _format_grounding_block(run, consensus_mode=True) == ""


# --- decision ledger renderer ---


def test_decision_ledger_renders_recent_events() -> None:
    run = _run_meta()
    block = _format_decision_ledger(run)
    assert block.startswith(LEDGER_HEADER)
    assert "- mode_route · DISCUSS" in block
    assert "- plan_gate · PLAN_GATE · draft approved" in block


def test_decision_ledger_caps_entries() -> None:
    run = {"goal_ledger": [{"event": f"e{i}", "phase": "DISCUSS"} for i in range(20)]}
    block = _format_decision_ledger(run, max_entries=3)
    lines = [ln for ln in block.splitlines() if ln.startswith("- ")]
    assert len(lines) == 3
    assert "- e19 · DISCUSS" in block
    assert "- e0 · DISCUSS" not in block


@pytest.mark.parametrize(
    "run",
    [
        {},
        {"goal_ledger": None},
        {"goal_ledger": []},
        {"goal_ledger": "nope"},
        {"goal_ledger": [None, 1, "x", {}]},
        {"goal_ledger": [{"note": "no event field"}]},
    ],
)
def test_decision_ledger_tolerates_garbage(run: dict[str, Any]) -> None:
    assert _format_decision_ledger(run) == ""


# --- flag gate ---


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "", "  ", "maybe"])
def test_antidrift_flag_not_enabled(val: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ANTIDRIFT", val)
    assert antidrift_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "TRUE", "On"])
def test_antidrift_flag_enabled(val: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_ANTIDRIFT", val)
    assert antidrift_enabled() is True


def test_antidrift_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_ANTIDRIFT", raising=False)
    assert antidrift_enabled() is False


# ===== Anti-drift B: unanimity red-team + fresh-eyes critic seat (ultragoal G003) =====


def _peer_reviewer_count(monkeypatch: pytest.MonkeyPatch, tmp_path: Any, *, antidrift: bool) -> int:
    """Run the PEER_REVIEW round under mock agents and count reviewer invocations."""
    import agent_lab.plan.workflow as pw

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    if antidrift:
        monkeypatch.setenv("AGENT_LAB_ANTIDRIFT", "1")
    else:
        monkeypatch.delenv("AGENT_LAB_ANTIDRIFT", raising=False)

    rounds: list[list[str]] = []

    def _fake_round(topic: str, messages: Any, agents: Any = None, **kwargs: Any) -> list[Any]:
        rounds.append([str(a) for a in (agents or [])])
        return []

    monkeypatch.setattr("agent_lab.room.run_parallel_round", _fake_round)
    folder = tmp_path / "sess"
    folder.mkdir(parents=True, exist_ok=True)
    pw.run_plan_peer_review_round(
        folder,
        topic="t",
        messages=[],
        agents=["codex", "claude", "cursor"],
        permissions=None,
        run_meta={},
        plan_md="# plan",
    )
    return len(rounds)


# AC10: PEER_REVIEW gains exactly one cold-context critic seat when ANTIDRIFT on; absent when off.


def test_fresh_eyes_seat_added_on_antidrift(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    base = _peer_reviewer_count(monkeypatch, tmp_path / "off", antidrift=False)
    with_seat = _peer_reviewer_count(monkeypatch, tmp_path / "on", antidrift=True)
    assert base == 1  # one peer-review round when off
    assert with_seat == base + 1  # exactly one extra cold-critic round when on


def test_fresh_eyes_guidance_is_cold_context() -> None:
    from agent_lab.plan.workflow import PLAN_FRESH_EYES_GUIDANCE

    assert "fresh-eyes" in PLAN_FRESH_EYES_GUIDANCE
    assert "이전 토론 맥락 없이" in PLAN_FRESH_EYES_GUIDANCE


def test_fresh_eyes_cold_round_uses_empty_history(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    import agent_lab.plan.workflow as pw

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_ANTIDRIFT", "1")
    captured: list[tuple[list[Any], str]] = []

    def _fake_round(topic: str, messages: Any, agents: Any = None, **kwargs: Any) -> list[Any]:
        captured.append((list(messages or []), str(kwargs.get("extra_follow_up") or "")))
        return []

    monkeypatch.setattr("agent_lab.room.run_parallel_round", _fake_round)
    folder = tmp_path / "sess"
    folder.mkdir()
    pw.run_plan_peer_review_round(
        folder,
        topic="t",
        messages=["prior discussion turn"],
        agents=["codex", "claude"],
        permissions=None,
        run_meta={},
        plan_md="# plan",
    )
    # Two rounds: normal peer review (with history) + cold fresh-eyes (empty history, cold guidance).
    assert len(captured) == 2
    cold_messages, cold_guidance = captured[-1]
    assert cold_messages == []
    assert "fresh-eyes" in cold_guidance


# AC8/AC9: unanimity red-team trigger — fires on 0-objection unanimity in the consensus path
# (panel-only by construction) when ANTIDRIFT on even if route.quality_gate is off; respects caps;
# never reachable in solo (run_consensus_agent_rounds is only called under consensus_mode).


def _redteam_should_fire(*, route_qg: bool, antidrift: bool, conflicts: int, agents: int, calls: int, cap: int) -> bool:
    """Mirror of the trigger predicate in run_consensus_agent_rounds (forced-review gate)."""
    antidrift_redteam = antidrift and not route_qg
    return (route_qg or antidrift_redteam) and conflicts == 0 and agents >= 2 and calls < cap


def test_redteam_fires_on_unanimity_when_antidrift_on() -> None:
    assert _redteam_should_fire(route_qg=False, antidrift=True, conflicts=0, agents=2, calls=0, cap=10) is True


def test_redteam_not_fired_when_both_off() -> None:
    assert _redteam_should_fire(route_qg=False, antidrift=False, conflicts=0, agents=2, calls=0, cap=10) is False


def test_redteam_not_fired_when_objections_present() -> None:
    assert _redteam_should_fire(route_qg=False, antidrift=True, conflicts=1, agents=2, calls=0, cap=10) is False


def test_redteam_respects_call_cap() -> None:
    # AC9: respects loop caps — never fires once calls have reached the cap.
    assert _redteam_should_fire(route_qg=False, antidrift=True, conflicts=0, agents=2, calls=10, cap=10) is False


def test_redteam_requires_two_agents() -> None:
    assert _redteam_should_fire(route_qg=False, antidrift=True, conflicts=0, agents=1, calls=0, cap=10) is False


def test_route_quality_gate_path_unaffected_by_antidrift() -> None:
    # When the route already has its quality gate, behavior is unchanged regardless of the flag.
    assert _redteam_should_fire(route_qg=True, antidrift=False, conflicts=0, agents=2, calls=0, cap=10) is True
    assert _redteam_should_fire(route_qg=True, antidrift=True, conflicts=0, agents=2, calls=0, cap=10) is True


def test_redteam_predicate_matches_source() -> None:
    # Guard against drift between this predicate mirror and the real condition string.
    import inspect

    from agent_lab.room import consensus_rounds

    src = inspect.getsource(consensus_rounds.run_consensus_agent_rounds)
    assert "antidrift_redteam = antidrift_enabled() and not route.quality_gate" in src
    assert "route.quality_gate or antidrift_redteam" in src
    assert "debate_conflicts == 0" in src
