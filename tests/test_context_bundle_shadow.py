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
        mailbox_rows=[],
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


def test_shadow_compare_bundle_includes_mailbox_rows_as_agent_opinion(monkeypatch: pytest.MonkeyPatch) -> None:
    """2026-07-16 -- mailbox_rows is the caller-captured unread_for_agent()
    result (read BEFORE build_mailbox_block's mark_delivered side effect),
    not something this function derives itself. adapt_mailbox_messages maps
    it to AGENT_OPINION, the same slot mailbox/peer/turn_bridge share."""
    _patch_reinvoked_producers(monkeypatch)
    rows = [{"id": "mail-1", "from": "codex", "body": "left a review comment", "ts": "2026-07-16T00:00:00Z"}]
    result = shadow_compare_bundle(**_base_kwargs(mailbox_rows=rows))
    assert result["ok"] is True
    assert "agent_opinion" in result["included_sources"]


def test_shadow_compare_bundle_includes_wisdom_and_playbook_on_r1(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """2026-07-16 -- wisdom_index_hits/playbook_bullets are R1-only, gated
    the same way context/bundle.py's own _append_wisdom_search_block/
    _append_playbook_block gate them. REPAIR_RECIPE's optional_sources
    includes SEMANTIC_MEMORY (unlike PLAN_RECIPE, used elsewhere in this
    file), so it's the activity that can demonstrate inclusion."""
    _patch_reinvoked_producers(monkeypatch)
    import agent_lab.wisdom.index as wisdom_index
    import agent_lab.wisdom.playbook as wisdom_playbook

    monkeypatch.setattr(
        wisdom_index, "search_wisdom_index",
        lambda folder, topic, **kw: [{"id": "doc-1", "snippet": "similar past fix", "score": 2.0}],
    )
    monkeypatch.setattr(wisdom_index, "wisdom_index_enabled", lambda run=None: True)
    monkeypatch.setattr(
        wisdom_playbook, "playbook_bullets_for_topic",
        lambda topic, k=3, **kw: [
            SimpleNamespace(
                id="b1", description="check for off-by-one first", pattern_id="p1",
                evidence_count=2, status="active", harness_rev="rev1", updated_at="2026-07-15",
            )
        ],
    )
    run_meta = {
        "mission_loop": {"enabled": True, "phase": "REPAIR"},
        "_session_folder": str(tmp_path),
        "artifacts": [{"id": "art-1", "summary": "failing test output", "ts": "2026-07-16"}],
    }
    kwargs = _base_kwargs(run_meta=run_meta, plan_md="# Plan\n\nfix the regression")
    result = shadow_compare_bundle(**kwargs)
    assert result["ok"] is True
    assert result["activity"] == "repair"
    assert "semantic_memory" in result["included_sources"]


def test_shadow_compare_bundle_skips_wisdom_and_playbook_when_not_r1(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Regression guard -- parallel_round != 1 must never call either
    producer at all (matching the real assembler's R1-only gate)."""
    _patch_reinvoked_producers(monkeypatch)
    import agent_lab.wisdom.index as wisdom_index
    import agent_lab.wisdom.playbook as wisdom_playbook

    calls = {"count": 0}

    def _boom(*args, **kwargs):
        calls["count"] += 1
        raise AssertionError("should not be called when parallel_round != 1")

    monkeypatch.setattr(wisdom_index, "search_wisdom_index", _boom)
    monkeypatch.setattr(wisdom_playbook, "playbook_bullets_for_topic", _boom)
    run_meta = {
        "mission_loop": {"enabled": True, "phase": "REPAIR"},
        "_session_folder": str(tmp_path),
        "artifacts": [{"id": "art-1", "summary": "failing test output", "ts": "2026-07-16"}],
    }
    kwargs = _base_kwargs(run_meta=run_meta, plan_md="# Plan\n\nfix the regression", parallel_round=2)
    result = shadow_compare_bundle(**kwargs)
    assert result["ok"] is True
    assert calls["count"] == 0
    assert "semantic_memory" not in result["included_sources"]


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
