from __future__ import annotations

from pathlib import Path

import pytest


def _session(tmp_path: Path) -> Path:
    folder = tmp_path / "m6-session"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    return folder


RETIRED_BRIDGE_FLAGS = {
    "AGENT_LAB_MISSION_DUAL_WRITE",
    "AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS",
    "AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY",
    "AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY",
    "AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY",
}


def test_dual_write_bridge_module_is_gone() -> None:
    """The bridge never activated under any profile; retired 2026-08-14."""
    import importlib

    for name in ("agent_lab.mission.dual_write", "agent_lab.mission.dual_write_observability"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(name)


def test_retired_bridge_flags_are_absent_from_registry_and_profiles() -> None:
    """No env or profile can bring the retired dual-write slices back.

    Slice 2 (inbox) was superseded by AGENT_LAB_MISSION_AUTHORITY in Wave B.
    Slices 1 (plan) and 3 (execution) shipped as "1" in four profiles but always
    resolved False because they gated on the never-enabled bridge, so they were
    removed 2026-08-14 along with mission/dual_write.py. Plan and execution writes
    remain on run.json.
    """
    from agent_lab.run.profile import list_profiles
    from agent_lab.runtime_flags import FLAG_REGISTRY

    registered = {row.name for row in FLAG_REGISTRY}
    assert RETIRED_BRIDGE_FLAGS.isdisjoint(registered)
    for cfg in list_profiles():
        assert RETIRED_BRIDGE_FLAGS.isdisjoint(cfg.flags), cfg.profile
        assert RETIRED_BRIDGE_FLAGS.isdisjoint(cfg.owns), cfg.profile


def test_inbox_authority_is_the_only_journal_write_path() -> None:
    """The surviving authority gate lives in inbox_application, not the bridge."""
    from agent_lab.mission.inbox_application import mission_authority_enabled
    from agent_lab.runtime_flags import FLAG_REGISTRY

    registered = {row.name for row in FLAG_REGISTRY}
    assert {"AGENT_LAB_MISSION_AUTHORITY", "AGENT_LAB_MISSION_AUTHORITY_SESSIONS"}.issubset(registered)
    assert callable(mission_authority_enabled)
