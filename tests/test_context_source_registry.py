"""CX1 (09-context-engineering.md) — source registry producers still exist.

Guards docs/redesign-2026-07/evidence/cx1-source-registry-2026-07-16.md §1:
every producer function named in the registry must still be importable, so
the doc can't silently drift from the real code (a module rename/deletion
should fail this test, not go unnoticed until CX2 tries to wire it up).
"""

from __future__ import annotations

import importlib


REGISTERED_PRODUCERS = (
    ("agent_lab.project_memory", "bootstrap_project_md"),
    ("agent_lab.workspace.md", "read_agents_md_for_injection"),
    ("agent_lab.workspace.md", "read_agents_md_hierarchy_for_injection"),
    ("agent_lab.workspace.md", "read_shared_context_for_injection"),
    ("agent_lab.repo_tree_context", "build_repo_tree_block"),
    ("agent_lab.repo_tree_context", "build_per_dir_agents_block"),
    ("agent_lab.session.guidance", "build_session_guidance_block"),
    ("agent_lab.reply_policy", "build_guidance_parts"),
    ("agent_lab.mission.notepad", "build_mission_wisdom_block"),
    ("agent_lab.runtime.context", "build_mission_wisdom_block"),
    ("agent_lab.steer", "drain_steer_follow_up"),
    ("agent_lab.wisdom.index", "search_wisdom_index"),
    ("agent_lab.wisdom.playbook", "playbook_bullets_for_topic"),
    ("agent_lab.wisdom.store", "wisdom_query"),
    ("agent_lab.wisdom.store", "wisdom_list_recent"),
    ("agent_lab.context.bundle", "_format_clarity_facts"),
    ("agent_lab.context.bundle", "_format_decision_ledger"),
    ("agent_lab.context.bundle", "_format_grounding_block"),
)


def test_all_registered_source_producers_still_exist() -> None:
    missing: list[str] = []
    for module_name, attr in REGISTERED_PRODUCERS:
        module = importlib.import_module(module_name)
        if not hasattr(module, attr):
            missing.append(f"{module_name}.{attr}")
    assert not missing, f"CX1 source registry references removed producer(s): {missing}"


def test_source_class_taxonomy_is_missing_agent_opinion() -> None:
    """§3 finding — recipe.py's SourceClass has 10 members, the doc's taxonomy has 11
    (agent_opinion is absent). This pins the gap so CX2 has to make an explicit
    decision instead of it silently staying unresolved."""
    from agent_lab.context.recipe import SourceClass

    assert "agent_opinion" not in {member.value for member in SourceClass}
    assert len(SourceClass) == 10
