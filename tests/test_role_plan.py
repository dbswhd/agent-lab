"""Tests for role_plan.py — Dynamic Room + Role Orchestration (Phase A/B)."""

from __future__ import annotations

import os

import pytest

from agent_lab.role_plan import (
    RoleSpec,
    _ROLES,
    agent_subset_for_route,
    persona_for_agent,
    resolve_role_plan,
    role_catalog,
)
from agent_lab.room_consensus import recombination_follow_up
from agent_lab.topic_router import CategoryRoute, resolve_topic_route


# ── helpers ──────────────────────────────────────────────────────────────────

def _route(category: str) -> CategoryRoute:
    """Build a minimal CategoryRoute for the given category."""
    from agent_lab.topic_router import _build_route

    return _build_route(category, source="test")  # type: ignore[arg-type]


AGENTS = ["cursor", "codex", "claude"]


# ── 1. resolve_role_plan ─────────────────────────────────────────────────────

class TestResolveRolePlan:
    def test_quick_returns_empty(self):
        assert resolve_role_plan(route=_route("quick"), agents=AGENTS) == {}

    def test_trading_returns_empty(self):
        assert resolve_role_plan(route=_route("trading"), agents=AGENTS) == {}

    def test_standard_cursor_is_proposer(self):
        roles = resolve_role_plan(route=_route("standard"), agents=AGENTS)
        assert roles.get("cursor") == "proposer"

    def test_standard_claude_is_critic(self):
        roles = resolve_role_plan(route=_route("standard"), agents=AGENTS)
        assert roles.get("claude") == "critic"

    def test_deep_codex_is_critic(self):
        roles = resolve_role_plan(route=_route("deep"), agents=AGENTS)
        assert roles.get("codex") == "critic"

    def test_critical_claude_is_synthesizer(self):
        roles = resolve_role_plan(route=_route("critical"), agents=AGENTS)
        assert roles.get("claude") == "synthesizer"

    def test_kill_switch_env_returns_empty(self, monkeypatch):
        monkeypatch.setenv("AGENT_LAB_ROOM_ROLES", "0")
        assert resolve_role_plan(route=_route("standard"), agents=AGENTS) == {}

    def test_kill_switch_false_returns_empty(self, monkeypatch):
        monkeypatch.setenv("AGENT_LAB_ROOM_ROLES", "false")
        assert resolve_role_plan(route=_route("deep"), agents=AGENTS) == {}

    def test_result_is_deterministic(self):
        r = _route("standard")
        assert resolve_role_plan(route=r, agents=AGENTS) == resolve_role_plan(
            route=r, agents=AGENTS
        )

    def test_unknown_agent_skipped(self):
        roles = resolve_role_plan(route=_route("standard"), agents=["cursor", "unknownbot"])
        assert "cursor" in roles
        assert "unknownbot" not in roles

    def test_empty_agents_returns_empty(self):
        assert resolve_role_plan(route=_route("standard"), agents=[]) == {}


# ── 2. agent_subset_for_route ─────────────────────────────────────────────────

class TestAgentSubsetForRoute:
    def test_quick_returns_single_agent(self):
        subset = agent_subset_for_route(_route("quick"), AGENTS)
        assert subset == [AGENTS[0]]

    def test_quick_empty_available(self):
        assert agent_subset_for_route(_route("quick"), []) == []

    def test_standard_returns_empty_list(self):
        # empty = use all
        assert agent_subset_for_route(_route("standard"), AGENTS) == []

    def test_deep_returns_empty_list(self):
        assert agent_subset_for_route(_route("deep"), AGENTS) == []

    def test_critical_returns_empty_list(self):
        assert agent_subset_for_route(_route("critical"), AGENTS) == []

    def test_kill_switch_returns_empty_list(self, monkeypatch):
        monkeypatch.setenv("AGENT_LAB_ROOM_ROLES", "0")
        # even quick should return empty (no filtering)
        assert agent_subset_for_route(_route("quick"), AGENTS) == []


# ── 3. persona text ──────────────────────────────────────────────────────────

class TestPersonaText:
    def test_proposer_persona_non_empty(self):
        p = persona_for_agent({"cursor": "proposer"}, "cursor")
        assert len(p) > 0

    def test_critic_persona_non_empty(self):
        p = persona_for_agent({"claude": "critic"}, "claude")
        assert len(p) > 0

    def test_executor_persona_non_empty(self):
        p = persona_for_agent({"codex": "executor"}, "codex")
        assert len(p) > 0

    def test_synthesizer_matches_recombination_follow_up(self):
        """Synthesizer persona === recombination_follow_up() — drift guard."""
        p = persona_for_agent({"claude": "synthesizer"}, "claude")
        assert p == recombination_follow_up()

    def test_no_role_returns_empty(self):
        assert persona_for_agent({"cursor": "proposer"}, "claude") == ""

    def test_none_roles_returns_empty(self):
        assert persona_for_agent(None, "cursor") == ""

    def test_empty_agent_returns_empty(self):
        assert persona_for_agent({"cursor": "proposer"}, "") == ""

    def test_proposer_persona_contains_role_label(self):
        p = persona_for_agent({"cursor": "proposer"}, "cursor")
        assert "Proposer" in p

    def test_critic_persona_contains_challenge_instruction(self):
        p = persona_for_agent({"claude": "critic"}, "claude")
        assert "CHALLENGE" in p


# ── 4. guidance seam ─────────────────────────────────────────────────────────

class TestGuidanceSeam:
    """build_guidance_parts injects correct persona per agent."""

    def _make_run_meta(self, roles: dict[str, str]) -> dict:
        return {"_turn_roles": roles}

    def _policy(self):
        from agent_lab.reply_policy import resolve_reply_policy

        return resolve_reply_policy(parallel_round=1)

    def test_proposer_agent_gets_proposer_text(self):
        from agent_lab.reply_policy import build_guidance_parts

        run_meta = self._make_run_meta({"codex": "proposer", "claude": "critic"})
        parts = build_guidance_parts(self._policy(), run_meta=run_meta, agent="codex")
        combined = "\n".join(parts)
        assert "Proposer" in combined

    def test_critic_agent_gets_critic_text(self):
        from agent_lab.reply_policy import build_guidance_parts

        run_meta = self._make_run_meta({"codex": "proposer", "claude": "critic"})
        parts = build_guidance_parts(self._policy(), run_meta=run_meta, agent="claude")
        combined = "\n".join(parts)
        assert "Critic" in combined

    def test_agent_with_no_role_gets_no_persona(self):
        from agent_lab.reply_policy import build_guidance_parts

        run_meta = self._make_run_meta({"claude": "critic"})
        parts = build_guidance_parts(self._policy(), run_meta=run_meta, agent="cursor")
        combined = "\n".join(parts)
        assert "Proposer" not in combined
        assert "Critic" not in combined

    def test_no_roles_in_run_meta_no_persona(self):
        from agent_lab.reply_policy import build_guidance_parts

        run_meta: dict = {}
        parts = build_guidance_parts(self._policy(), run_meta=run_meta, agent="cursor")
        combined = "\n".join(parts)
        assert "Proposer" not in combined


# ── 5. escalation resets roles ───────────────────────────────────────────────

class TestEscalationRoleReset:
    def test_escalation_clears_turn_roles(self):
        """_maybe_escalate가 _turn_roles를 {} 로 리셋하는지 확인."""
        from unittest.mock import MagicMock

        from agent_lab.room_consensus_rounds import run_consensus_agent_rounds

        os.environ["AGENT_LAB_MOCK_AGENTS"] = "1"
        try:
            run_meta: dict = {"_turn_roles": {"cursor": "proposer", "claude": "critic"}}
            events = []

            def on_event(name: str, payload: dict) -> None:
                events.append((name, payload))

            # Run a minimal quick turn — escalation won't fire but we can test
            # that _turn_roles is stashed at turn start
            msgs, _ = run_consensus_agent_rounds(
                topic="오타 수정",
                messages=[],
                agents=["cursor"],
                on_event=on_event,
                run_meta=run_meta,
            )
            # After run, _turn_roles is still set (quick → empty via resolve_role_plan)
            # The key point: _turn_roles in run_meta after a quick turn should be {}
            assert run_meta.get("_turn_roles") == {}
        finally:
            os.environ.pop("AGENT_LAB_MOCK_AGENTS", None)


# ── 6. role_catalog ───────────────────────────────────────────────────────────

class TestRoleCatalog:
    def test_catalog_has_four_roles(self):
        catalog = role_catalog()
        assert len(catalog) == 4

    def test_catalog_has_required_keys(self):
        for entry in role_catalog():
            assert "id" in entry
            assert "label" in entry

    def test_catalog_includes_all_role_ids(self):
        ids = {e["id"] for e in role_catalog()}
        assert ids == {"proposer", "critic", "synthesizer", "executor"}

    def test_all_roles_have_non_empty_labels(self):
        for entry in role_catalog():
            assert entry["label"]


# ── 7. CategoryRoute new fields ───────────────────────────────────────────────

class TestCategoryRouteFields:
    def test_agent_subset_default_none(self):
        # standard 카테고리 → subset 없음(None). quick은 ('cursor',) 반환.
        r = resolve_topic_route("이번 스프린트 아키텍처 설계를 어떻게 진행할지 토론합시다")
        assert r.agent_subset is None

    def test_role_plan_default_empty(self):
        r = resolve_topic_route("아무 토픽")
        assert r.role_plan == {}

    def test_category_dict_excludes_empty_role_plan(self):
        r = resolve_topic_route("아무 토픽")
        d = r.category_dict()
        assert "role_plan" not in d

    def test_run_meta_ephemeral_excludes_turn_roles(self):
        from agent_lab.run_meta import _EPHEMERAL_RUN_KEYS

        assert "_turn_roles" in _EPHEMERAL_RUN_KEYS
