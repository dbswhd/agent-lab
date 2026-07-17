from __future__ import annotations

from pathlib import Path

from agent_lab.mission.application import MissionApplication
from agent_lab.mission.kernel import MissionState
from agent_lab.mission.projection import apply_mission_loop_status_projection
from agent_lab.run.meta import patch_run_meta, read_run_meta


def _session(tmp_path: Path) -> Path:
    folder = tmp_path / "session-m6"
    folder.mkdir()
    (folder / "plan.md").write_text("# Ship\n\n- do it\n", encoding="utf-8")
    (folder / "run.json").write_text(
        '{"plan_workflow":{"enabled":true,"phase":"HUMAN_PENDING"}}\n',
        encoding="utf-8",
    )
    return folder


def test_mission_status_projection_does_not_patch_identical_lifecycle_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    folder = _session(tmp_path)
    application = MissionApplication(folder, "Ship")
    mission = application.approve_plan()
    calls = 0

    def count_patch(*_args, **_kwargs):
        nonlocal calls
        calls += 1

    monkeypatch.setattr("agent_lab.mission.projection.patch_run_meta", count_patch)

    apply_mission_loop_status_projection(folder, mission)

    assert calls == 0
    assert read_run_meta(folder)["mission_loop"]["phase"] == "EXECUTE_QUEUE"


def test_mission_status_projection_repairs_stale_compatibility_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    folder = _session(tmp_path)
    application = MissionApplication(folder, "Ship")
    mission = application.approve_plan()

    def stale(run):
        run["mission_loop"]["phase"] = "DISCUSS"
        return run

    patch_run_meta(folder, stale)
    calls = 0

    def count_patch(*args, **kwargs):
        nonlocal calls
        calls += 1
        from agent_lab.run.meta import patch_run_meta as real_patch

        return real_patch(*args, **kwargs)

    monkeypatch.setattr("agent_lab.mission.projection.patch_run_meta", count_patch)

    apply_mission_loop_status_projection(folder, mission)

    assert calls == 1
    assert read_run_meta(folder)["mission_loop"]["phase"] == "EXECUTE_QUEUE"


def test_duplicate_mission_approval_repairs_rows_without_duplicate_mission_events(tmp_path: Path) -> None:
    folder = _session(tmp_path)
    application = MissionApplication(folder, "Ship")
    first = application.approve_plan()
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    before = journal.read_text(encoding="utf-8")

    run = read_run_meta(folder)
    run["mission_loop"]["phase"] = "DISCUSS"
    run["plan_workflow"]["phase"] = "HUMAN_PENDING"

    def stale(run):
        run["mission_loop"]["phase"] = "DISCUSS"
        run["plan_workflow"]["phase"] = "HUMAN_PENDING"
        return run

    patch_run_meta(folder, stale)

    duplicate = application.approve_plan()

    assert duplicate == first
    assert journal.read_text(encoding="utf-8") == before
    repaired = read_run_meta(folder)
    assert repaired["mission_loop"]["phase"] == "EXECUTE_QUEUE"
    assert repaired["plan_workflow"]["phase"] == "APPROVED"
    assert duplicate.state is MissionState.READY_TO_EXECUTE


def test_commit_to_row_patch_crash_repairs_on_idempotent_retry(tmp_path: Path, monkeypatch) -> None:
    folder = _session(tmp_path)
    application = MissionApplication(folder, "Ship")
    original = MissionApplication._project_plan
    crashed = False

    def crash_once(self, mission, *, note="", phase=None):
        nonlocal crashed
        if not crashed:
            crashed = True
            raise RuntimeError("injected mission-commit-to-row-patch crash")
        return original(self, mission, note=note, phase=phase)

    monkeypatch.setattr(MissionApplication, "_project_plan", crash_once)

    try:
        application.approve_plan()
    except RuntimeError as exc:
        assert str(exc) == "injected mission-commit-to-row-patch crash"
    else:
        raise AssertionError("injected crash did not fire")

    retried = application.approve_plan()

    assert retried.state is MissionState.READY_TO_EXECUTE
    assert read_run_meta(folder)["plan_workflow"]["phase"] == "APPROVED"


def test_side_effect_to_mission_commit_crash_is_repaired_without_duplicate_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    folder = _session(tmp_path)
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", folder.name)
    monkeypatch.setenv("AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY", "1")
    from agent_lab.human_inbox import create_inbox_item, resolve_inbox_item
    import agent_lab.mission.dual_write as dual_write

    item = create_inbox_item(folder, kind="question", source="m6", prompt="Choose", options=[{"id": "a"}])
    original = dual_write.commit_inbox_resolution
    crashed = False

    def crash_once(*args, **kwargs):
        nonlocal crashed
        if not crashed:
            crashed = True
            raise RuntimeError("injected side-effect-to-mission-commit crash")
        return original(*args, **kwargs)

    monkeypatch.setattr(dual_write, "commit_inbox_resolution", crash_once)
    resolve_inbox_item(folder, item["id"], decision="a", append_chat=False)

    try:
        dual_write.commit_inbox_resolution(folder, item_id=item["id"], answer="a")
    except RuntimeError as exc:
        assert str(exc) == "injected side-effect-to-mission-commit crash"
    else:
        raise AssertionError("injected crash did not fire")

    retried = dual_write.commit_inbox_resolution(folder, item_id=item["id"], answer="a")

    assert retried["mirrored"] is False
    assert retried["reason"] == "inbox_write_authority_disabled"
    mission = MissionApplication(folder, "Ship").load()
    assert mission.open_gates == ()
    assert read_run_meta(folder)["human_inbox"][0]["status"] == "resolved"
