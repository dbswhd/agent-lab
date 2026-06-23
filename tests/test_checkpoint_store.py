"""Checkpoint/resume layer (AGENT_LAB_CHECKPOINT) — AC1-AC11 + Critic N1/N2.

Snapshot the run.json FSM subset at each phase transition via the patch_run_meta chokepoint
to a per-session checkpoints.jsonl (capped 200, drop-oldest); resume_from_checkpoint restores
the FSM subset then stops. Default-off; per-flag OFF-parity is the primary invariant.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_lab import checkpoint_store
from agent_lab.checkpoint_store import (
    CHECKPOINT_CAP,
    CHECKPOINT_FSM_KEYS,
    CHECKPOINTS_FILE,
    list_checkpoints,
    resume_from_checkpoint,
)
from agent_lab.run_meta import patch_run_meta, read_run_meta, write_run_meta


def _seed(folder: Path, phase: str = "DISCUSS") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    write_run_meta(
        folder,
        {
            "workflow_id": "room.parallel",
            "mission_loop": {"enabled": True, "phase": phase},
            "plan_workflow": {"enabled": True, "phase": "DRAFT"},
            "goal_ledger": [{"event": "seed"}],
            "token_budget": {"limit": 100},
        },
    )


def _set_mission_phase(folder: Path, phase: str) -> None:
    def _u(run: dict[str, Any]) -> dict[str, Any]:
        ml = dict(run.get("mission_loop") or {})
        ml["phase"] = phase
        run["mission_loop"] = ml
        return run

    patch_run_meta(folder, _u)


def _checkpoints_file(folder: Path) -> Path:
    return folder / CHECKPOINTS_FILE


# --- AC1: flag on + phase change appends exactly one snapshot ---


def test_ac1_phase_change_appends_one_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CHECKPOINT", "1")
    folder = tmp_path / "s"
    _seed(folder, "DISCUSS")
    _set_mission_phase(folder, "EXECUTE_QUEUE")
    records = list_checkpoints(folder)
    assert len(records) == 1
    assert records[0]["prior_phase"] == ["DISCUSS", "DRAFT"]
    assert records[0]["next_phase"] == ["EXECUTE_QUEUE", "DRAFT"]


# --- AC2: no phase change => no snapshot ---


def test_ac2_no_phase_change_no_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CHECKPOINT", "1")
    folder = tmp_path / "s"
    _seed(folder, "DISCUSS")

    def _u(run: dict[str, Any]) -> dict[str, Any]:
        run["completed_steps"] = ["x"]  # mutate a non-phase field
        return run

    patch_run_meta(folder, _u)
    assert list_checkpoints(folder) == []
    assert not _checkpoints_file(folder).exists()


# --- AC3: roundtrip restore equals snapshot ---


def test_ac3_roundtrip_restore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CHECKPOINT", "1")
    folder = tmp_path / "s"
    _seed(folder, "DISCUSS")
    _set_mission_phase(folder, "EXECUTE_QUEUE")  # snapshot n=0 captures next=EXECUTE_QUEUE
    _set_mission_phase(folder, "VERIFY")  # now run is at VERIFY
    assert read_run_meta(folder)["mission_loop"]["phase"] == "VERIFY"

    restored = resume_from_checkpoint(folder, 0)
    # checkpoint n=0 captured the post-transition state (EXECUTE_QUEUE)
    assert restored["mission_loop"]["phase"] == "EXECUTE_QUEUE"
    assert read_run_meta(folder)["mission_loop"]["phase"] == "EXECUTE_QUEUE"


# --- AC4 + AC11: resume restores then stops; appends no checkpoint ---


def test_ac4_ac11_resume_stops_and_appends_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CHECKPOINT", "1")
    folder = tmp_path / "s"
    _seed(folder, "DISCUSS")
    _set_mission_phase(folder, "EXECUTE_QUEUE")
    before = len(list_checkpoints(folder))
    resume_from_checkpoint(folder, 0)
    after = len(list_checkpoints(folder))
    assert after == before  # AC11: restore wrote via write_run_meta, no capture hook fired
    # AC4: no execution/tick artifacts — restore only touched run.json FSM keys
    run = read_run_meta(folder)
    assert "executions" not in run or run.get("executions") in (None, [])


# --- AC5: OFF-parity — flag off => no write, byte-identical ---


def test_ac5_off_parity_no_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_CHECKPOINT", raising=False)
    folder = tmp_path / "s"
    _seed(folder, "DISCUSS")
    _set_mission_phase(folder, "EXECUTE_QUEUE")
    assert not _checkpoints_file(folder).exists()
    assert list_checkpoints(folder) == []


def test_ac5_off_parity_run_json_byte_identical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The run.json content produced with the flag off must equal the flag-on content
    # (checkpoint capture is side-channel only; it never alters run.json bytes).
    monkeypatch.delenv("AGENT_LAB_CHECKPOINT", raising=False)
    off = tmp_path / "off"
    _seed(off, "DISCUSS")
    _set_mission_phase(off, "EXECUTE_QUEUE")
    off_bytes = (off / "run.json").read_text(encoding="utf-8")

    monkeypatch.setenv("AGENT_LAB_CHECKPOINT", "1")
    on = tmp_path / "on"
    _seed(on, "DISCUSS")
    _set_mission_phase(on, "EXECUTE_QUEUE")
    on_bytes = (on / "run.json").read_text(encoding="utf-8")

    assert off_bytes == on_bytes


# --- AC6: retention cap 200 drop-oldest ---


def test_ac6_retention_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CHECKPOINT", "1")
    folder = tmp_path / "s"
    _seed(folder, "DISCUSS")
    phases = ["EXECUTE_QUEUE", "VERIFY", "REPAIR", "DISCUSS"]
    for i in range(CHECKPOINT_CAP + 10):
        _set_mission_phase(folder, phases[i % len(phases)])
    records = list_checkpoints(folder)
    assert len(records) == CHECKPOINT_CAP  # capped
    # oldest dropped: n values are monotonic and the earliest retained n > 0
    assert records[0]["n"] > 0
    assert records[-1]["n"] == records[0]["n"] + CHECKPOINT_CAP - 1


# --- AC7: snapshot scope = FSM subset only ---


def test_ac7_snapshot_scope_fsm_subset_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CHECKPOINT", "1")
    folder = tmp_path / "s"
    _seed(folder, "DISCUSS")

    def _u(run: dict[str, Any]) -> dict[str, Any]:
        ml = dict(run.get("mission_loop") or {})
        ml["phase"] = "EXECUTE_QUEUE"
        run["mission_loop"] = ml
        run["chat_pointer"] = "should-not-be-snapshotted"
        run["plan_md_inline"] = "nope"
        return run

    patch_run_meta(folder, _u)
    fsm_state = list_checkpoints(folder)[0]["fsm_state"]
    assert set(fsm_state).issubset(set(CHECKPOINT_FSM_KEYS))
    assert "chat_pointer" not in fsm_state
    assert "plan_md_inline" not in fsm_state


# --- AC8: crash_recovery untouched + import-lane contract ---


def test_ac8_no_forbidden_cross_lane_import() -> None:
    # checkpoint_store must stay pure (no room/mission/plan_execute imports at module level)
    import inspect

    src = inspect.getsource(checkpoint_store)
    for banned in ("agent_lab.room", "agent_lab.mission_loop", "agent_lab.plan_execute", "agent_lab.runtime"):
        # allow the lazy run_meta import only; banned lanes must be absent entirely
        assert banned not in src, f"checkpoint_store must not import {banned}"


def test_ac8_crash_recovery_module_unchanged_import() -> None:
    # Importing checkpoint_store must not perturb crash_recovery import (independence smoke).
    from agent_lab import crash_recovery

    assert hasattr(crash_recovery, "reconcile_crashed_merges")


# --- AC10: no FSM phase transition persists via a direct write_run_meta bypass ---


def test_ac10_phase_setters_route_through_patch_run_meta() -> None:
    # Source guard: plan_workflow.set_plan_workflow_phase uses patch_run_meta (not a bare
    # write_run_meta), so the chokepoint sees plan-workflow transitions.
    import inspect

    from agent_lab import plan_workflow

    src = inspect.getsource(plan_workflow.set_plan_workflow_phase)
    assert "patch_run_meta" in src
    assert "write_run_meta" not in src


def test_ac10_behavioral_plan_workflow_transition_captured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CHECKPOINT", "1")
    from agent_lab.plan_workflow import set_plan_workflow_phase

    folder = tmp_path / "s"
    _seed(folder, "DISCUSS")
    set_plan_workflow_phase(folder, "PEER_REVIEW")  # real plan_workflow transition
    records = list_checkpoints(folder)
    assert len(records) == 1
    assert records[0]["next_phase"][1] == "PEER_REVIEW"


# --- Critic N2: snapshot keys == restore keys (shared constant, no drift) ---


def test_n2_snapshot_and_restore_use_same_key_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CHECKPOINT", "1")
    folder = tmp_path / "s"
    _seed(folder, "DISCUSS")
    _set_mission_phase(folder, "EXECUTE_QUEUE")
    snap_keys = set(list_checkpoints(folder)[0]["fsm_state"])
    # restore reads from the same CHECKPOINT_FSM_KEYS; the snapshot keys are a subset of it
    assert snap_keys.issubset(set(CHECKPOINT_FSM_KEYS))
    # the seeded run had all-but-some keys; assert the captured set matches what was present
    assert snap_keys == {"mission_loop", "plan_workflow", "goal_ledger", "token_budget"}


# --- flag gate ---


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "", "  ", "maybe"])
def test_flag_not_enabled(val: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CHECKPOINT", val)
    assert checkpoint_store.checkpoint_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "On"])
def test_flag_enabled(val: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CHECKPOINT", val)
    assert checkpoint_store.checkpoint_enabled() is True


def test_resume_missing_checkpoint_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CHECKPOINT", "1")
    folder = tmp_path / "s"
    _seed(folder, "DISCUSS")
    with pytest.raises(KeyError):
        resume_from_checkpoint(folder, 99)
