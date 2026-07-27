"""P1: the typed plan artifact — parse once at write time, and say why a plan is dead.

The failure modes pinned here are the ones measured across 874 real session plans:
8.2% yielded zero executable actions, 44 of them because the scribe wrote a readable
plan with no recognised section header, and 28 because the plan was a stub.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_lab.plan.artifact import (
    PLAN_ARTIFACT_SCHEMA_VERSION,
    build_plan_artifact,
    diagnose_plan,
    plan_artifact_for,
    plan_artifact_path,
    plan_artifact_public,
    plan_execution_blocker,
    read_plan_artifact,
    refresh_plan_artifact,
    write_plan_artifact,
)
from agent_lab.plan.paths import write_session_plan_md
from agent_lab.plan.pending import plan_content_hash

EXECUTABLE_PLAN = """# Title

## 지금 실행

1. Fix the typo
   - 무엇을: correct `roompy` to `room.py`
   - 어디서: `docs/x2-lift.md`
   - 검증: `grep -c 'room.py' docs/x2-lift.md`
"""

# The dangerous real-world shape: reads fine to a human, invisible to the executor.
NO_HEADER_PLAN = """# X2 lift dogfood

## TL;DR

> Summary: Fix one typo in the dogfood evidence row.

## Notes

Some prose that never declares an executable section.
"""

STUB_PLAN = "# X2 lift dogfood"


# --- diagnostics name the real failure modes -------------------------------


def test_executable_plan_has_no_diagnostics() -> None:
    assert diagnose_plan(EXECUTABLE_PLAN) == ()


def test_no_section_header_is_named_precisely() -> None:
    diagnostics = diagnose_plan(NO_HEADER_PLAN)
    assert [d.code for d in diagnostics] == ["no_section_header"]
    assert "지금 실행" in diagnostics[0].hint


def test_stub_plan_is_named_precisely() -> None:
    diagnostics = diagnose_plan(STUB_PLAN)
    assert [d.code for d in diagnostics] == ["empty_plan"]


def test_empty_plan_is_a_stub() -> None:
    assert [d.code for d in diagnose_plan("")] == ["empty_plan"]


def test_header_without_numbered_items() -> None:
    plan = "# T\n\n## 지금 실행\n\nSome prose but no numbered list at all.\n"
    assert [d.code for d in diagnose_plan(plan)] == ["no_numbered_items"]


def test_items_missing_required_fields() -> None:
    plan = "# T\n\n## 지금 실행\n\n1. Do the thing\n   - 무엇을: something\n"
    assert [d.code for d in diagnose_plan(plan)] == ["incomplete_action_fields"]


# --- artifact construction --------------------------------------------------


def test_artifact_captures_executable_actions() -> None:
    artifact = build_plan_artifact(EXECUTABLE_PLAN)
    assert artifact.is_executable
    assert artifact.executable_count == 1
    assert artifact.diagnostics == ()
    assert artifact.plan_hash == plan_content_hash(EXECUTABLE_PLAN)
    assert artifact.executable_actions[0]["what"] == "correct `roompy` to `room.py`"


def test_artifact_records_diagnostics_for_dead_plan() -> None:
    artifact = build_plan_artifact(NO_HEADER_PLAN)
    assert not artifact.is_executable
    assert artifact.executable_count == 0
    assert [d.code for d in artifact.diagnostics] == ["no_section_header"]


# --- persistence round-trip -------------------------------------------------


def test_artifact_round_trips(tmp_path: Path) -> None:
    artifact = build_plan_artifact(EXECUTABLE_PLAN)
    write_plan_artifact(tmp_path, artifact)
    loaded = read_plan_artifact(tmp_path)
    assert loaded is not None
    assert loaded.plan_hash == artifact.plan_hash
    assert loaded.executable_count == artifact.executable_count
    assert loaded.to_dict() == artifact.to_dict()


def test_missing_artifact_reads_as_none(tmp_path: Path) -> None:
    assert read_plan_artifact(tmp_path) is None


def test_corrupt_artifact_reads_as_none(tmp_path: Path) -> None:
    path = plan_artifact_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert read_plan_artifact(tmp_path) is None


def test_future_schema_version_is_rejected(tmp_path: Path) -> None:
    path = plan_artifact_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": PLAN_ARTIFACT_SCHEMA_VERSION + 1, "plan_hash": "x"}),
        encoding="utf-8",
    )
    assert read_plan_artifact(tmp_path) is None


# --- staleness and backward compatibility -----------------------------------


def test_stale_artifact_is_rebuilt_not_trusted(tmp_path: Path) -> None:
    """A plan edited without refreshing the artifact must not serve stale actions."""
    refresh_plan_artifact(tmp_path, NO_HEADER_PLAN)
    fresh = plan_artifact_for(tmp_path, EXECUTABLE_PLAN)
    assert fresh.is_executable
    assert fresh.plan_hash == plan_content_hash(EXECUTABLE_PLAN)


def test_sessions_without_an_artifact_still_work(tmp_path: Path) -> None:
    """Backward compatibility: pre-P1 sessions get an artifact built on demand."""
    assert read_plan_artifact(tmp_path) is None
    artifact = plan_artifact_for(tmp_path, EXECUTABLE_PLAN)
    assert artifact.is_executable


def test_refresh_survives_unwritable_folder(tmp_path: Path) -> None:
    """Artifact persistence must never break plan writing."""
    missing = tmp_path / "nope" / "deeper"
    artifact = refresh_plan_artifact(missing, EXECUTABLE_PLAN)
    assert artifact.is_executable


# --- the write seam produces the artifact -----------------------------------


def test_plan_write_seam_refreshes_artifact(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    run_meta: dict = {}
    write_session_plan_md(folder, EXECUTABLE_PLAN, run_meta)

    stored = read_plan_artifact(folder)
    assert stored is not None
    assert stored.is_executable
    assert stored.plan_hash == plan_content_hash((folder / "plan.md").read_text(encoding="utf-8"))


def test_plan_write_seam_records_dead_plan(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    write_session_plan_md(folder, NO_HEADER_PLAN, {})

    stored = read_plan_artifact(folder)
    assert stored is not None
    assert not stored.is_executable
    assert [d.code for d in stored.diagnostics] == ["no_section_header"]


# --- the loud surface -------------------------------------------------------


def test_blocker_is_none_for_executable_plan(tmp_path: Path) -> None:
    assert plan_execution_blocker(tmp_path, EXECUTABLE_PLAN) is None


def test_blocker_explains_dead_plan(tmp_path: Path) -> None:
    message = plan_execution_blocker(tmp_path, NO_HEADER_PLAN)
    assert message is not None
    assert "executable section header" in message
    assert "지금 실행" in message


def test_public_payload_shape() -> None:
    payload = plan_artifact_public(build_plan_artifact(NO_HEADER_PLAN))
    assert payload["is_executable"] is False
    assert payload["executable_count"] == 0
    assert payload["diagnostics"][0]["code"] == "no_section_header"


# --- plan gate carries the diagnostic --------------------------------------


def test_plan_gate_reports_the_specific_cause(tmp_path: Path) -> None:
    from agent_lab.mission.loop import evaluate_plan_gate

    result = evaluate_plan_gate(NO_HEADER_PLAN)
    assert result["status"] == "reject"
    assert result["reason"] == "no_section_header"
    assert "executable section header" in result["detail"]
    assert result["diagnostics"][0]["code"] == "no_section_header"


def test_plan_gate_distinguishes_stub_from_missing_header() -> None:
    from agent_lab.mission.loop import evaluate_plan_gate

    assert evaluate_plan_gate(STUB_PLAN)["reason"] == "empty_plan"
    assert evaluate_plan_gate(NO_HEADER_PLAN)["reason"] == "no_section_header"


def test_plan_gate_still_passes_a_good_plan() -> None:
    from agent_lab.mission.loop import evaluate_plan_gate

    result = evaluate_plan_gate(EXECUTABLE_PLAN)
    assert result["status"] == "ok"
    assert result["action_count"] == 1


# --- artifact agrees with the legacy parser on real-world shapes ------------


def test_artifact_actions_match_direct_parse() -> None:
    """The typed artifact must be a faithful index, not a second opinion."""
    from agent_lab.plan.actions import parse_plan_actions

    for plan in (EXECUTABLE_PLAN, NO_HEADER_PLAN, STUB_PLAN, ""):
        artifact = build_plan_artifact(plan)
        direct = [a.to_dict() for a in parse_plan_actions(plan)]
        assert list(artifact.actions) == direct
