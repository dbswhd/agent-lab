from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.server.main import create_app
from scripts.mission_authority_cohort_matrix import (
    AUTHORITY_MATRIX,
    apply_cohort,
    route_probe,
)


def test_matrix_covers_independent_allowlists_and_explicit_overlap() -> None:
    assert {
        (row.plan_authority, row.inbox_authority, row.overlap)
        for row in AUTHORITY_MATRIX
    } == {
        (True, False, False),
        (False, True, False),
        (True, True, True),
        (False, False, False),
    }


@pytest.mark.parametrize(
    ("cohort_name", "plan_authority", "inbox_authority"),
    [
        ("plan-only", True, False),
        ("inbox-only", False, True),
        ("both", True, True),
        ("neither", False, False),
    ],
)
def test_real_routes_follow_matrix_without_changing_noncohort_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cohort_name: str,
    plan_authority: bool,
    inbox_authority: bool,
) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", sessions)
    apply_cohort(monkeypatch.setenv, cohort_name)

    with TestClient(create_app(bootstrap=False)) as client:
        result = route_probe(client, sessions, cohort_name)

    assert result.plan_authority is plan_authority
    assert result.inbox_authority is inbox_authority
    assert result.plan_status == 200
    assert result.inbox_create_status == 200
    assert result.inbox_resolve_status == 200
    assert result.duplicate_status == 409
    assert result.malformed_status == 422


def test_empty_allowlists_preserve_legacy_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", sessions)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_AUTHORITY", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", "")
    monkeypatch.setenv("AGENT_LAB_MISSION_AUTHORITY_SESSIONS", "")

    with TestClient(create_app(bootstrap=False)) as client:
        result = route_probe(client, sessions, "empty")

    assert result.plan_authority is False
    assert result.inbox_authority is False
    assert result.plan_bridge_reason == "cohort_allowlist_empty"
    assert result.legacy_inbox_written is True
