"""Scheduled mission tick — verify fail → REPAIR → reverify pass E2E."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.mission_loop import enable_mission_loop, maybe_advance_mission, on_verify_result
from agent_lab.mission_tick import run_scheduled_mission_tick
from agent_lab.run_meta import patch_run_meta, read_run_meta
from agent_lab.trust_budget import set_trust_budget


@pytest.fixture
def sessions_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import agent_lab.mission_scheduler as sched_mod
    import agent_lab.session as session_mod
    import app.server.deps as deps_mod

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(sched_mod, "SESSIONS_DIR", tmp_path)
    return tmp_path


def _merged_fail_execution(*, execution_id: str = "exec-repair-1") -> dict:
    return {
        "id": execution_id,
        "status": "merged",
        "action_index": 1,
        "isolation_effective": "worktree",
        "source_touched_paths": ["docs/README.md"],
        "action_verify": "make test",
        "oracle": {"verdict": "fail", "detail": "tests red"},
    }


def _repair_state(
    run: dict,
    *,
    execution: dict | None = None,
    pending: list[int] | None = None,
) -> dict:
    run["gate_profile"] = "assistant"
    exec_row = execution or _merged_fail_execution()
    run["executions"] = [exec_row]
    ml = run.setdefault("mission_loop", {})
    ml.update(
        {
            "enabled": True,
            "phase": "REPAIR",
            "current_action_index": 1,
            "pending_action_indices": pending if pending is not None else [1],
            "last_execution_id": exec_row["id"],
            "action_repair_counts": {"1": 1},
            "autonomous_segment": {"active": False},
        }
    )
    return run


def test_scheduled_tick_repair_passes_to_mission_done(sessions_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = sessions_env / "repair-pass"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    enable_mission_loop(folder, start_autonomous=False)
    patch_run_meta(folder, _repair_state)

    def _fake_reverify(folder_arg, execution_id, **kwargs):
        on_verify_result(folder_arg, action_index=1, verdict="pass")
        return {
            "execution": {
                "id": execution_id,
                "status": "merged",
                "oracle": {"verdict": "pass"},
            },
            "repair": {"status": "merged", "attempt": 1},
        }

    monkeypatch.setattr(
        "agent_lab.plan_execute.reverify_merged_execution",
        _fake_reverify,
    )

    result = run_scheduled_mission_tick(folder, schedule_id="s-repair", sandbox=False)
    assert result["ok"] is True
    ml = result["mission_loop"]
    assert ml.get("status") == "repair_complete"
    assert ml.get("oracle_verdict") == "pass"
    assert read_run_meta(folder)["mission_loop"]["phase"] == "MISSION_DONE"
    steps = ml.get("conductor_steps") or []
    assert len(steps) == 1
    assert steps[0].get("status") == "repair_complete"


def test_maybe_advance_scheduled_repair(sessions_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = sessions_env / "repair-advance"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    enable_mission_loop(folder)
    patch_run_meta(folder, _repair_state)

    monkeypatch.setattr(
        "agent_lab.plan_execute.reverify_merged_execution",
        lambda folder_arg, execution_id, **kwargs: (
            on_verify_result(folder_arg, action_index=1, verdict="pass"),
            {
                "execution": {"id": execution_id, "oracle": {"verdict": "pass"}},
                "repair": {"status": "merged"},
            },
        )[1],
    )

    out = maybe_advance_mission(folder, scheduled=True)
    assert out.get("status") == "repair_complete"
    assert read_run_meta(folder)["mission_loop"]["phase"] == "MISSION_DONE"


def test_scheduled_conductor_merge_fail_repair_pass_chain(sessions_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """MERGE_REVIEW → verify fail → REPAIR → reverify pass in one scheduled tick."""
    folder = sessions_env / "repair-chain"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    enable_mission_loop(folder, start_autonomous=False)
    set_trust_budget(
        folder,
        {"auto_merge_remaining": 1, "classifier_allow": ["docs_only"]},
    )

    def _merge_review(run: dict) -> dict:
        run["gate_profile"] = "assistant"
        run["executions"] = [
            {
                "id": "exec-a1",
                "status": "pending_approval",
                "action_index": 1,
                "isolation_effective": "apply",
                "source_touched_paths": ["docs/README.md"],
                "action_verify": "make test",
            }
        ]
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "MERGE_REVIEW",
                "current_action_index": 1,
                "pending_action_indices": [1],
                "last_execution_id": "exec-a1",
                "autonomous_segment": {"active": False},
            }
        )
        return run

    patch_run_meta(folder, _merge_review)

    def _fake_auto_merge(folder_arg, *, execution_id):
        def _mark_merged(run: dict) -> dict:
            for row in run.get("executions") or []:
                if isinstance(row, dict) and row.get("id") == execution_id:
                    row["status"] = "merged"
                    row["oracle"] = {"verdict": "fail", "detail": "tests red"}
            return run

        patch_run_meta(folder_arg, _mark_merged)
        on_verify_result(folder_arg, action_index=1, verdict="fail", reason="tests red")
        return {"auto_merge": {"eligible": True}, "execution": {"id": execution_id}}

    def _fake_reverify(folder_arg, execution_id, **kwargs):
        on_verify_result(folder_arg, action_index=1, verdict="pass")
        return {
            "execution": {
                "id": execution_id,
                "status": "merged",
                "oracle": {"verdict": "pass"},
            },
            "repair": {"status": "merged", "attempt": 1},
        }

    monkeypatch.setattr("agent_lab.auto_merge.resolve_auto_merge", _fake_auto_merge)
    monkeypatch.setattr(
        "agent_lab.plan_execute.reverify_merged_execution",
        _fake_reverify,
    )

    result = run_scheduled_mission_tick(folder, schedule_id="s-chain", sandbox=False)
    assert result["ok"] is True
    ml = result["mission_loop"]
    assert ml.get("status") == "repair_complete"
    run = read_run_meta(folder)
    assert run["mission_loop"]["phase"] == "MISSION_DONE"
    statuses = [step.get("status") for step in (ml.get("conductor_steps") or [])]
    assert statuses == ["auto_merge_complete", "repair_complete"]


def test_scheduled_conductor_execute_merge_fail_repair_pass(
    sessions_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EXECUTE_QUEUE → dry-run → merge → verify fail → REPAIR → pass."""
    folder = sessions_env / "repair-full"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    plan = """# Plan

## 지금 실행

1. Fix docs
   - 무엇을: update README
   - 어디서: `docs/README.md`
   - 검증: `make test`
"""
    (folder / "plan.md").write_text(plan, encoding="utf-8")
    enable_mission_loop(folder, start_autonomous=False)
    set_trust_budget(
        folder,
        {"auto_merge_remaining": 1, "classifier_allow": ["docs_only"]},
    )

    def _queue(run: dict) -> dict:
        run["gate_profile"] = "assistant"
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "EXECUTE_QUEUE",
                "current_action_index": 1,
                "pending_action_indices": [1],
                "autonomous_segment": {"active": False},
            }
        )
        return run

    patch_run_meta(folder, _queue)

    def _fake_dry_run(folder_arg, action_index, **kwargs):
        exec_row = {
            "id": "exec-a1",
            "action_index": action_index,
            "status": "pending_approval",
            "source_touched_paths": ["docs/README.md"],
            "action_verify": "make test",
            "isolation_effective": "apply",
        }

        def _append(run: dict) -> dict:
            run["executions"] = list(run.get("executions") or []) + [exec_row]
            return run

        patch_run_meta(folder_arg, _append)
        return exec_row

    def _fake_auto_merge(folder_arg, *, execution_id):
        def _mark_merged(run: dict) -> dict:
            for row in run.get("executions") or []:
                if isinstance(row, dict) and row.get("id") == execution_id:
                    row["status"] = "merged"
                    row["oracle"] = {"verdict": "fail", "detail": "tests red"}
            return run

        patch_run_meta(folder_arg, _mark_merged)
        on_verify_result(folder_arg, action_index=1, verdict="fail", reason="tests red")
        return {"auto_merge": {"eligible": True}, "execution": {"id": execution_id}}

    def _fake_reverify(folder_arg, execution_id, **kwargs):
        on_verify_result(folder_arg, action_index=1, verdict="pass")
        return {
            "execution": {"id": execution_id, "oracle": {"verdict": "pass"}},
            "repair": {"status": "merged", "attempt": 1},
        }

    monkeypatch.setattr("agent_lab.plan_execute.run_dry_run", _fake_dry_run)
    monkeypatch.setattr("agent_lab.auto_merge.resolve_auto_merge", _fake_auto_merge)
    monkeypatch.setattr(
        "agent_lab.plan_execute.reverify_merged_execution",
        _fake_reverify,
    )

    result = run_scheduled_mission_tick(folder, schedule_id="s-full", sandbox=False)
    assert result["ok"] is True
    run = read_run_meta(folder)
    assert run["mission_loop"]["phase"] == "MISSION_DONE"
    statuses = [step.get("status") for step in (result["mission_loop"].get("conductor_steps") or [])]
    assert statuses == ["dry_run_complete", "auto_merge_complete", "repair_complete"]
