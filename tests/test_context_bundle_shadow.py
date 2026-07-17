"""CX8 (09-context-engineering.md §11) — src/agent_lab/context/bundle_shadow.py.

Exercises shadow_compare_bundle directly (not through build_context_bundle
yet -- see test_context_bundle.py for the splice-point integration test).
Covers: no-activity-mapping skip, a successful comparison for a mapped
phase, and the "never raises" contract when a producer call fails.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_lab.context.bundle_shadow import shadow_compare_bundle
from agent_lab.core.context_bundle import ContextBundle, ContextBundleMeta


def _legacy_bundle(text: str = "legacy rendered text") -> ContextBundle:
    return ContextBundle(
        constraints=text,
        plan_open="",
        bridge="",
        recent="",
        peer="",
        guidance_block="",
        connect_hint="",
        meta=ContextBundleMeta(agent="claude", parallel_round=1, review_mode=False),
    )


def _base_kwargs(**overrides):
    kwargs = dict(
        run_meta={"mission_loop": {"enabled": True, "phase": "DISCUSS"}},
        agent="claude",
        topic="fix the bug",
        plan_md="# Plan\n\nship it",
        parallel_round=1,
        session_guidance="guidance text",
        session_skills="",
        resume_block="",
        plugin_block="",
        cap_block="",
        team_block="",
        objection_block="",
        challenge_block="",
        plan_open="[plan 미결]\n- item 1",
        turn_state_block="",
        bridge_block="",
        peer_block="",
        guidance_parts=["be concise"],
        envelope_block="",
        tool_rules="",
        recent_msgs=[],
        legacy_bundle=_legacy_bundle(),
    )
    kwargs.update(overrides)
    return kwargs


def test_shadow_compare_bundle_returns_skip_for_unmapped_phase() -> None:
    result = shadow_compare_bundle(**_base_kwargs(run_meta={"mission_loop": {"enabled": True, "phase": "MISSION_DONE"}}))
    assert result is not None
    assert result["ok"] is False
    assert result.get("skipped") is True


def test_shadow_compare_bundle_returns_skip_when_no_mission_loop() -> None:
    result = shadow_compare_bundle(**_base_kwargs(run_meta={}))
    assert result["ok"] is False
    assert result.get("skipped") is True


def _patch_reinvoked_producers(monkeypatch: pytest.MonkeyPatch) -> None:
    """PLAN_RECIPE requires PROJECT_DOC and REPO_CONTEXT, both sourced from
    the 5 producers shadow_compare_bundle re-invokes directly (see module
    docstring) -- those read real workspace state (git repo tree, AGENTS.md
    on disk) that doesn't exist for a synthetic run_meta in a unit test.
    Patch them at their defining module so the local `from X import Y`
    inside shadow_compare_bundle picks up the stub."""
    import agent_lab.repo_tree_context as repo_tree_context
    import agent_lab.workspace.md as workspace_md

    monkeypatch.setattr(repo_tree_context, "build_repo_tree_block", lambda run_meta, **kw: "[Repo tree]\n- src/")
    monkeypatch.setattr(
        workspace_md, "read_agents_md_hierarchy_for_injection", lambda run_meta, plan_md="", **kw: "AGENTS.md guidance"
    )


def test_shadow_compare_bundle_succeeds_for_a_mapped_phase(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_reinvoked_producers(monkeypatch)
    result = shadow_compare_bundle(**_base_kwargs())
    assert result is not None
    assert result["ok"] is True
    assert result["activity"] == "plan"
    assert isinstance(result["included_count"], int)
    assert isinstance(result["recipe_total_tokens"], int)
    assert isinstance(result["included_sources"], list)
    assert result["legacy_total_chars"] == len(_legacy_bundle().render())


def test_shadow_compare_bundle_includes_recent_messages_and_dispatch_content(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_reinvoked_producers(monkeypatch)
    recent = [
        SimpleNamespace(role="user", agent=None, content="please fix it", ts="2026-07-16T00:00:00Z", parallel_round=None),
        SimpleNamespace(role="agent", agent="claude", content="working on it", ts="2026-07-16T00:00:01Z", parallel_round=1),
    ]
    result = shadow_compare_bundle(**_base_kwargs(recent_msgs=recent))
    assert result["ok"] is True
    assert "human_intent" in result["included_sources"]


def test_shadow_compare_bundle_never_raises_on_producer_failure() -> None:
    """A malformed run_meta (mission_loop isn't a dict) must not propagate
    as an exception -- the live turn must be unaffected regardless of what
    goes wrong in the shadow pass."""
    result = shadow_compare_bundle(**_base_kwargs(run_meta={"mission_loop": "not-a-dict"}))
    assert result is not None
    assert result["ok"] is False


def test_shadow_compare_bundle_always_returns_a_dict_never_none() -> None:
    """Contract: shadow_compare_bundle itself always returns a dict (ok
    True or False) -- returning None on "flag off" is build_context_bundle's
    job, checked BEFORE this function is ever called, not this function's."""
    result = shadow_compare_bundle(**_base_kwargs())
    assert result is not None
