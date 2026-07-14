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


def test_retired_authority_env_and_profiles_cannot_reenable_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", folder.name)
    for name in (
        "AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY",
        "AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY",
        "AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY",
    ):
        monkeypatch.setenv(name, "1")

    from agent_lab.mission.dual_write import (
        execution_write_authority_enabled,
        inbox_write_authority_enabled,
        plan_write_authority_enabled,
    )
    from agent_lab.run.profile import list_profiles
    from agent_lab.runtime_flags import FLAG_REGISTRY

    assert plan_write_authority_enabled(folder) is False
    assert inbox_write_authority_enabled(folder) is False
    assert execution_write_authority_enabled(folder) is False
    assert all(
        all(name not in cfg.flags and name not in cfg.owns for cfg in list_profiles())
        for name in (
            "AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY",
            "AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY",
            "AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY",
        )
    )
    registered = {row.name for row in FLAG_REGISTRY}
    assert not registered.intersection(
        {
            "AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY",
            "AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY",
            "AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY",
        }
    )
