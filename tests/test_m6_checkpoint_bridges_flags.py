from __future__ import annotations

from pathlib import Path

import pytest


def _session(tmp_path: Path) -> Path:
    folder = tmp_path / "m6-session"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    return folder


def test_dual_write_empty_allowlist_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.delenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", raising=False)

    from agent_lab.mission.dual_write import dual_write_enabled, mirror_plan_approval

    assert dual_write_enabled(folder) is False
    result = mirror_plan_approval(folder, goal="ship")
    assert result["mirrored"] is False
    assert result["reason"] == "cohort_allowlist_empty"
    assert not (folder / ".agent-lab" / "mission-events.jsonl").exists()


def test_retired_inbox_authority_env_and_profiles_cannot_reenable_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Slice 2 (inbox) stays retired -- superseded by AGENT_LAB_MISSION_AUTHORITY (Wave B).

    Slice 1 (plan) and Slice 3 (execution) were re-enabled 2026-07-23 -- see
    tests/test_mission_dual_write.py::test_plan_write_authority_on_mission_first_then_side_effects
    and ::test_execution_write_authority_commit_approve for their live behavior.
    """
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", folder.name)
    monkeypatch.setenv("AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY", "1")

    from agent_lab.mission.dual_write import inbox_write_authority_enabled
    from agent_lab.run.profile import list_profiles
    from agent_lab.runtime_flags import FLAG_REGISTRY

    assert inbox_write_authority_enabled(folder) is False
    assert all(
        "AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY" not in cfg.flags
        and "AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY" not in cfg.owns
        for cfg in list_profiles()
    )
    registered = {row.name for row in FLAG_REGISTRY}
    assert "AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY" not in registered
    assert {"AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY", "AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY"}.issubset(
        registered
    )
