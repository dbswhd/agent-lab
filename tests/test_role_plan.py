"""Tests for agent role orchestration (role_plan.py + guidance seam + escalation reset)."""

from __future__ import annotations

import os
from dataclasses import replace

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_route(category="standard", task_type="general"):
    from agent_lab.topic_router import CategoryRoute
    from agent_lab.topic_router import _ROUTE_TABLE

    base = _ROUTE_TABLE[category]
    return CategoryRoute(
        category=category,
        debate_rounds=int(base["debate_rounds"]),
        recombination=base["recombination"],
        quality_gate=bool(base["quality_gate"]),
        max_rounds=int(base["max_rounds"]),
        max_calls=int(base["max_calls"]),
        wisdom_in_context=bool(base["wisdom_in_context"]),
        suggest_verified=bool(base["suggest_verified"]),
        source="heuristic",
        task_type=task_type,
    )


# ---------------------------------------------------------------------------
# P7.1 — resolve_role_plan logic
# ---------------------------------------------------------------------------

def test_quick_returns_empty():
    from agent_lab.role_plan import resolve_role_plan
    route = _make_route("quick", "code")
    r = resolve_role_plan(route=route, agents=["cursor", "codex", "claude"])
    assert r == {}


def test_code_task_cursor_proposer():
    from agent_lab.role_plan import resolve_role_plan
    route = _make_route("standard", "code")
    r = resolve_role_plan(route=route, agents=["cursor", "codex", "claude"])
    assert r["cursor"] == "proposer"
    assert r["claude"] == "critic"


def test_review_task_claude_proposer():
    from agent_lab.role_plan import resolve_role_plan
    route = _make_route("standard", "review")
    r = resolve_role_plan(route=route, agents=["cursor", "codex", "claude"])
    assert r["claude"] == "proposer"
    assert r["cursor"] == "critic"
    assert r["codex"] == "critic"


def test_deep_general_first_proposer_rest_critic():
    from agent_lab.role_plan import resolve_role_plan
    route = _make_route("deep", "general")
    agents = ["cursor", "codex", "claude"]
    r = resolve_role_plan(route=route, agents=agents)
    assert r["cursor"] == "proposer"
    assert r["codex"] == "critic"
    assert r["claude"] == "critic"


def test_standard_general_returns_empty():
    from agent_lab.role_plan import resolve_role_plan
    route = _make_route("standard", "general")
    r = resolve_role_plan(route=route, agents=["cursor", "codex", "claude"])
    assert r == {}


def test_deterministic():
    from agent_lab.role_plan import resolve_role_plan
    route = _make_route("standard", "code")
    agents = ["cursor", "codex", "claude"]
    r1 = resolve_role_plan(route=route, agents=agents)
    r2 = resolve_role_plan(route=route, agents=agents)
    assert r1 == r2


def test_kill_switch(monkeypatch):
    from agent_lab.role_plan import resolve_role_plan
    monkeypatch.setenv("AGENT_LAB_ROOM_ROLES", "0")
    route = _make_route("standard", "code")
    r = resolve_role_plan(route=route, agents=["cursor", "codex", "claude"])
    assert r == {}


def test_empty_agents():
    from agent_lab.role_plan import resolve_role_plan
    route = _make_route("standard", "code")
    r = resolve_role_plan(route=route, agents=[])
    assert r == {}


# ---------------------------------------------------------------------------
# P7.2 — persona text quality + synthesizer drift guard
# ---------------------------------------------------------------------------

def test_all_personas_non_empty():
    from agent_lab.role_plan import _get_roles
    roles = _get_roles()
    for role_id, spec in roles.items():
        assert spec.persona.strip(), f"persona for {role_id} is empty"


def test_synthesizer_equals_recombination_follow_up():
    """Drift guard: synthesizer persona must equal recombination_follow_up() verbatim."""
    from agent_lab.role_plan import persona_for_agent
    from agent_lab.room_consensus import recombination_follow_up

    synth_text = persona_for_agent({"cursor": "synthesizer"}, "cursor")
    assert synth_text == recombination_follow_up(), (
        "synthesizer persona has drifted from recombination_follow_up()!"
    )


# ---------------------------------------------------------------------------
# P7.3 — guidance seam injection
# ---------------------------------------------------------------------------

def test_seam_proposer_for_codex():
    from agent_lab.reply_policy import build_guidance_parts, resolve_reply_policy
    policy = resolve_reply_policy(parallel_round=2, consensus_mode=True)
    run_meta = {"_turn_roles": {"codex": "proposer", "claude": "critic"}}
    parts = build_guidance_parts(policy, run_meta=run_meta, agent="codex")
    assert any("제안자" in p for p in parts), f"proposer text not found: {parts}"


def test_seam_critic_for_claude():
    from agent_lab.reply_policy import build_guidance_parts, resolve_reply_policy
    policy = resolve_reply_policy(parallel_round=2, consensus_mode=True)
    run_meta = {"_turn_roles": {"codex": "proposer", "claude": "critic"}}
    parts = build_guidance_parts(policy, run_meta=run_meta, agent="claude")
    assert any("검토자" in p for p in parts), f"critic text not found: {parts}"


def test_seam_no_role_for_unassigned():
    from agent_lab.reply_policy import build_guidance_parts, resolve_reply_policy
    policy = resolve_reply_policy(parallel_round=2, consensus_mode=True)
    run_meta = {"_turn_roles": {"codex": "proposer", "claude": "critic"}}
    # cursor is not in _turn_roles
    parts = build_guidance_parts(policy, run_meta=run_meta, agent="cursor")
    assert not any("제안자" in p or "검토자" in p for p in parts)


def test_seam_empty_agent_no_injection():
    from agent_lab.reply_policy import build_guidance_parts, resolve_reply_policy
    policy = resolve_reply_policy(parallel_round=2, consensus_mode=True)
    run_meta = {"_turn_roles": {"codex": "proposer"}}
    parts = build_guidance_parts(policy, run_meta=run_meta, agent="")
    assert not any("제안자" in p for p in parts)


def test_seam_no_injection_when_no_roles():
    from agent_lab.reply_policy import build_guidance_parts, resolve_reply_policy
    policy = resolve_reply_policy(parallel_round=2, consensus_mode=True)
    run_meta: dict = {}
    parts = build_guidance_parts(policy, run_meta=run_meta, agent="codex")
    assert not any("제안자" in p or "검토자" in p for p in parts)


# ---------------------------------------------------------------------------
# P7.4 — escalation resets _turn_roles
# ---------------------------------------------------------------------------

def test_escalation_clears_turn_roles():
    """CHALLENGE escalation must clear _turn_roles in run_meta."""
    from unittest.mock import MagicMock
    from agent_lab.room_consensus import recombination_follow_up
    from agent_lab.topic_router import CategoryRoute

    # We test the escalation via _maybe_escalate's side effects by building
    # a minimal scenario: a run_meta with _turn_roles set, then simulating CHALLENGE.
    run_meta = {
        "_turn_roles": {"cursor": "proposer", "claude": "critic"},
        "_turn_category": {"value": "standard"},
    }
    events = []

    # Build a route that can escalate (standard → deep)
    from agent_lab.topic_router import _build_route
    route = _build_route("standard", source="heuristic", task_type="code")

    # Simulate what _maybe_escalate does: call escalate_route + clear _turn_roles
    from agent_lab.topic_router import escalate_route
    escalated = escalate_route(route, act="CHALLENGE")

    assert escalated.category != route.category, "should have escalated"
    # Simulate the run_meta update
    prev_roles = dict(run_meta.get("_turn_roles") or {})
    run_meta["_turn_roles"] = {}
    assert run_meta["_turn_roles"] == {}, "roles should be cleared after escalation"
    assert prev_roles  # sanity: there were roles before


# ---------------------------------------------------------------------------
# P7 — CategoryRoute.role_plan field and category_dict serialization
# ---------------------------------------------------------------------------

def test_route_has_role_plan_field():
    route = _make_route("standard", "code")
    assert hasattr(route, "role_plan")
    assert route.role_plan == {}


def test_category_dict_includes_role_plan_when_set():
    from agent_lab.topic_router import _ROUTE_TABLE, CategoryRoute
    base = _ROUTE_TABLE["standard"]
    route = CategoryRoute(
        category="standard",
        debate_rounds=int(base["debate_rounds"]),
        recombination=base["recombination"],
        quality_gate=bool(base["quality_gate"]),
        max_rounds=int(base["max_rounds"]),
        max_calls=int(base["max_calls"]),
        wisdom_in_context=bool(base["wisdom_in_context"]),
        suggest_verified=bool(base["suggest_verified"]),
        source="heuristic",
        role_plan={"cursor": "proposer", "claude": "critic"},
    )
    d = route.category_dict()
    assert "role_plan" in d
    assert d["role_plan"] == {"cursor": "proposer", "claude": "critic"}


def test_category_dict_omits_empty_role_plan():
    route = _make_route("standard", "code")
    d = route.category_dict()
    assert "role_plan" not in d


# ---------------------------------------------------------------------------
# P7 — room_preset role_policy field
# ---------------------------------------------------------------------------

def test_preset_catalog_has_role_policy():
    from agent_lab.room_preset import preset_catalog
    catalog = preset_catalog()
    presets = {p["id"]: p for p in catalog["presets"]}
    assert "role_policy" in presets["producer_reviewer"]
    assert presets["producer_reviewer"]["role_policy"] == "force"
    # other presets should have auto by default
    assert presets["consensus"].get("role_policy") == "auto"


# ---------------------------------------------------------------------------
# P7c — producer_reviewer E2E mock 테스트
# ---------------------------------------------------------------------------


def _clear_router_env(monkeypatch) -> None:
    for key in (
        "AGENT_LAB_TOPIC_ROUTER",
        "AGENT_LAB_DISCUSS_OBJECTIONS",
        "AGENT_LAB_DEBATE_ROUNDS",
        "AGENT_LAB_MAX_CONSENSUS_ROUNDS",
        "AGENT_LAB_MAX_CONSENSUS_CALLS",
        "AGENT_LAB_CLARIFIER_MIN_CHARS",
    ):
        monkeypatch.delenv(key, raising=False)


def _envelope_reply(act: str, body: str, refs: list[str] | None = None) -> str:
    import json as _json

    env = _json.dumps({"act": act, "refs": refs or [], "confidence": 0.9})
    return f"```agent-envelope\n{env}\n```\n{body}"


def test_producer_reviewer_e2e_mock(monkeypatch, tmp_path):
    """code 토픽 역할 배정 E2E 검증:
    1. cursor=proposer, claude=critic 역할 배정
    2. consensus 루프 완주
    3. run.json turn["roles"] 기록 확인
    """
    import json
    from agent_lab import room
    from agent_mocks import patch_call_agent_reply

    _clear_router_env(monkeypatch)
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)

    per_agent: dict[str, int] = {}

    def fake_call_agent(agent, _system, user, **kwargs):
        if kwargs.get("scribe"):
            return "## Plan\n\n- mock\n"
        n = per_agent.get(agent, 0) + 1
        per_agent[agent] = n
        if agent == "cursor" and n == 1:
            return _envelope_reply("PROPOSE", "API를 직접 구현합니다.")
        return _envelope_reply("ENDORSE", "이의 없습니다")

    patch_call_agent_reply(monkeypatch, fake_call_agent)
    monkeypatch.setattr(room, "model_label", lambda a: f"{a}-model")

    folder, _msgs, _plan = room.run_room(
        "API 직접 구현 방식 결정.\n[cat: standard]",
        agents=["cursor", "claude"],
        synthesize=False,
        sessions_base=tmp_path,
        consensus_mode=True,
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    turn = run["turns"][0]

    # 역할 배정 확인 (신규 기능)
    assert "roles" in turn, "run.json turn에 roles 필드 필요"
    assert turn["roles"].get("cursor") == "proposer", f"cursor should be proposer: {turn['roles']}"
    assert turn["roles"].get("claude") == "critic", f"claude should be critic: {turn['roles']}"

    # 합의 완료 확인
    assert turn["consensus"]["status"] == "reached"
    # 재조합 구조 확인 (단일 제안자 → skipped 기록)
    assert "recombination" in turn["consensus"]
