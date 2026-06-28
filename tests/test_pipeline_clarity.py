"""G002 — dedicated clarity scorer + concrete-anchor detection."""

from __future__ import annotations

import pytest

from agent_lab import clarity


@pytest.mark.parametrize(
    "text",
    [
        "fix src/agent_lab/run_meta.py",
        "implement #42",
        "fix processKeywordDetector",
        "update UserModel",
        "patch user_model",
        "add login - acceptance criteria: returns 401",
        "add ```ts const x = 1 ```",
    ],
)
def test_detect_concrete_anchors_true(text: str) -> None:
    assert clarity.detect_concrete_anchors(text) is True


@pytest.mark.parametrize("text", ["make it better", "improve the app", "do the thing", ""])
def test_detect_concrete_anchors_false(text: str) -> None:
    assert clarity.detect_concrete_anchors(text) is False


def test_score_ambiguity_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    assert clarity.score_ambiguity("fix src/foo.py") == 0.0
    assert clarity.score_ambiguity("make it better") == 0.8
    assert clarity.score_ambiguity("") == 1.0


def test_clarity_threshold_met(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    anchored = {"verified_loop": {"loop_goal": {"text": "fix src/foo.py null check"}}}
    vague = {"verified_loop": {"loop_goal": {"text": "make it better"}}}
    assert clarity.clarity_threshold_met(anchored) is True
    assert clarity.clarity_threshold_met(vague) is False


def test_parse_score_conservative() -> None:
    assert clarity._parse_score("0.2") == 0.2
    assert clarity._parse_score("ambiguity is 0.9 overall") == 0.9
    assert clarity._parse_score("no number here") == 0.8


def test_score_panel_live_queries_each_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """The lateral panel calls every agent once and aggregates per-dimension means."""
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "0")
    calls: list[tuple[str, str]] = []

    def fake_call_agent(agent, system, user, **_kwargs):
        calls.append((str(agent), user))
        # codex sees it clearer; claude vaguer — mean is taken per dimension.
        if agent == "codex":
            return "goal=0.2 constraints=0.2 criteria=0.2 context=0.2"
        return "goal=0.6 constraints=0.6 criteria=0.6 context=0.6"

    monkeypatch.setattr("agent_lab.agents.registry.available_agents", lambda: ["codex", "claude"])
    monkeypatch.setattr("agent_lab.agents.registry.call_agent", fake_call_agent)
    result = clarity.score_clarity("improve holistic reliability")
    assert {a for a, _ in calls} == {"codex", "claude"}  # every panelist queried
    # per-dimension mean of 0.2 and 0.6 = 0.4
    assert result["dimensions"]["goal"] == 0.4
    assert result["overall"] == 0.4  # uniform => coverage-weighted == mean
    assert set(result["panel"]) == {"codex", "claude"}


def test_score_panel_missing_dimension_is_conservative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "0")
    monkeypatch.setattr("agent_lab.agents.registry.available_agents", lambda: ["codex"])
    monkeypatch.setattr(
        "agent_lab.agents.registry.call_agent",
        lambda *a, **k: "goal=0.1",  # only one dimension reported
    )
    dims = clarity.score_clarity("improve reliability")["dimensions"]
    assert dims["goal"] == 0.1
    assert dims["criteria"] == 0.8  # missing => conservative vague


def test_dimensions_multi_signal_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    dims = clarity.score_clarity("improve reliability with tests and verify expected output")["dimensions"]
    assert dims["criteria"] == 0.3  # verify/tests signal
    assert dims["goal"] == 0.8  # still vague goal


def test_coverage_weighted_overall() -> None:
    # 0.6*max + 0.4*mean
    dims = {"goal": 0.8, "constraints": 0.8, "criteria": 0.0, "context": 0.8}
    expected = round(0.6 * 0.8 + 0.4 * (0.8 + 0.8 + 0.0 + 0.8) / 4, 4)
    assert clarity._coverage_weighted_overall(dims) == expected


def test_weakest_dimension(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    # criteria clear, others vague => weakest is one of the vague ones (not criteria)
    result = clarity.score_clarity("ship it with tests and verify output")
    assert result["weakest"] != "criteria"


def test_lateral_questions_target_weak_dimensions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    qs = clarity.lateral_questions("make it better")
    cats = [q["category"] for q in qs]
    assert len(qs) == 3  # capped at max_q
    assert all(c in clarity.CLARITY_DIMENSIONS for c in cats)


def test_lateral_questions_none_when_anchored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    assert clarity.lateral_questions("fix src/foo.py null check") == []


def test_question_loop_generates_then_answer_advances(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Full loop: vague => questions persisted; concrete answer => threshold met."""
    import json

    from agent_lab.run.meta import read_run_meta
    from agent_lab.session.clarifier import record_clarifier_answers

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "mission_loop": {"enabled": True, "phase": "CLARIFY"},
                "verified_loop": {"loop_goal": {"text": "make it better"}},
            }
        ),
        encoding="utf-8",
    )
    assert clarity.clarity_threshold_met(read_run_meta(tmp_path)) is False

    interview = clarity.ensure_clarify_questions(tmp_path)
    assert interview and interview["questions"]
    # panel score persisted for observability
    assert read_run_meta(tmp_path)["mission_loop"]["clarity"]["overall"] == 0.8

    # idempotent: second call does not replace the pending interview
    again = clarity.ensure_clarify_questions(tmp_path)
    assert again["created_at"] == interview["created_at"]

    qid = interview["questions"][0]["id"]
    record_clarifier_answers(
        tmp_path, answers={qid: "ship login fix in src/auth/login.py, acceptance criteria returns 401"}
    )
    assert clarity.clarity_threshold_met(read_run_meta(tmp_path)) is True


# --- topology (AGENT_LAB_CLARITY_TOPOLOGY, opt-in component-level scoring) ---


def test_topology_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.delenv("AGENT_LAB_CLARITY_TOPOLOGY", raising=False)
    result = clarity.score_clarity("add login and improve the dashboard")
    assert "components" not in result  # backward compatible: no extra surface when off


def test_topology_decomposes_and_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CLARITY_TOPOLOGY", "1")
    result = clarity.score_clarity("add login with tests, then improve the dashboard")
    comps = result["components"]
    assert len(comps) >= 2
    # sorted vaguest-first
    assert comps == sorted(comps, key=lambda c: c["overall"], reverse=True)
    assert result["weakest_component"] == comps[0]["id"]
    for c in comps:
        assert set(c["dimensions"]) == set(clarity.CLARITY_DIMENSIONS)


def test_topology_single_component_when_no_split(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CLARITY_TOPOLOGY", "1")
    comps = clarity.score_components("make it better")
    assert len(comps) == 1
    assert comps[0]["name"] == "overall"


def test_topology_lateral_questions_are_component_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CLARITY_TOPOLOGY", "1")
    qs = clarity.lateral_questions("add login and improve the dashboard")
    assert qs
    for q in qs:
        assert "component" in q  # each question names the vague part
        assert q["prompt"].startswith(f"[{q['component']}]")


def test_topology_anchored_still_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CLARITY_TOPOLOGY", "1")
    # anchored => early return, no components, no questions
    assert clarity.lateral_questions("fix src/foo.py null check") == []


def test_topology_live_single_decompose_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "0")
    monkeypatch.setenv("AGENT_LAB_CLARITY_TOPOLOGY", "1")
    calls: list[str] = []

    def fake_call_agent(agent, system, user, **_kwargs):
        calls.append(str(system))
        return (
            "component=auth | goal=0.2 constraints=0.3 criteria=0.4 context=0.5\n"
            "component=ui | goal=0.7 constraints=0.7 criteria=0.7 context=0.7"
        )

    monkeypatch.setattr("agent_lab.agents.registry.available_agents", lambda: ["codex", "claude"])
    monkeypatch.setattr("agent_lab.agents.registry.call_agent", fake_call_agent)
    comps = clarity.score_components("build auth and ui")
    assert [c["name"] for c in comps] == ["ui", "auth"]  # vaguest first
    assert len(calls) == 1  # exactly one decompose call (panel[:1])


# --- established_facts (confirmed answers -> mission_loop.clarity.facts -> context) ---


def _seed_clarify_run(tmp_path, goal: str = "make it better") -> None:
    import json

    (tmp_path / "run.json").write_text(
        json.dumps(
            {"mission_loop": {"enabled": True, "phase": "CLARIFY"}, "verified_loop": {"loop_goal": {"text": goal}}}
        ),
        encoding="utf-8",
    )


def test_established_facts_extract_and_persist(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.run.meta import read_run_meta
    from agent_lab.session.clarifier import record_clarifier_answers

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    _seed_clarify_run(tmp_path)
    iv = clarity.ensure_clarify_questions(tmp_path)
    qids = [q["id"] for q in iv["questions"]]
    record_clarifier_answers(tmp_path, answers={qids[0]: "done = returns 401", qids[1]: "do not touch billing"})
    facts = clarity.extract_established_facts(tmp_path)
    assert len(facts) == 2
    answers = {f["answer"] for f in facts}
    assert "done = returns 401" in answers
    # persisted
    persisted = read_run_meta(tmp_path)["mission_loop"]["clarity"]["facts"]
    assert len(persisted) == 2
    # idempotent: re-run keyed by question id, no duplicates
    again = clarity.extract_established_facts(tmp_path)
    assert len(again) == 2


def test_established_facts_empty_when_unanswered(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    _seed_clarify_run(tmp_path)
    clarity.ensure_clarify_questions(tmp_path)
    assert clarity.extract_established_facts(tmp_path) == []


def test_format_facts_block() -> None:
    run = {
        "mission_loop": {
            "clarity": {
                "facts": [
                    {"id": "q1", "category": "goal", "answer": "returns 401"},
                    {"id": "q2", "category": "constraints", "component": "auth", "answer": "no billing changes"},
                ]
            }
        }
    }
    block = clarity.format_facts_block(run)
    assert block.startswith("[확정 사실 · clarify]")
    assert "[goal] returns 401" in block
    assert "[auth/constraints] no billing changes" in block
    assert clarity.format_facts_block({"mission_loop": {}}) == ""


def test_facts_injected_into_context_constraints(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.context.bundle import build_context_bundle
    from agent_lab.run.meta import read_run_meta
    from agent_lab.session.clarifier import record_clarifier_answers

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    _seed_clarify_run(tmp_path)
    iv = clarity.ensure_clarify_questions(tmp_path)
    record_clarifier_answers(tmp_path, answers={iv["questions"][0]["id"]: "done = returns 401 on bad creds"})
    clarity.extract_established_facts(tmp_path)
    run = read_run_meta(tmp_path)

    bundle = build_context_bundle("topic", [], "codex", run_meta=run)
    assert "확정 사실 · clarify" in bundle.constraints
    assert "returns 401" in bundle.constraints
    # absent when no facts
    plain = build_context_bundle("topic", [], "codex", run_meta={"mission_loop": {}})
    assert "확정 사실 · clarify" not in plain.constraints
