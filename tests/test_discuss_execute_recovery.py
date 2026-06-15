from pathlib import Path

from agent_lab.mission_loop import maybe_advance_mission


def _make_run(tmp_path: Path, *, phase: str = "DISCUSS", pending: bool = False):
    run = {
        "mission_loop": {
            "enabled": True,
            "circuit_breaker": False,
            "phase": phase,
            "plan_gate": {},
            "pending_executions": [],
            "autonomous_segment": {"active": True},
            "discuss_recovery": {
                "pending": pending,
                "reason": "verify_fail",
                "action_index": 0,
                "started_at": None,
                "completed_at": None,
            },
        },
        "schedule_sandbox": False,
        "policy": {},
        "turn_budget": {},
    }
    return run


def test_maybe_advance_mission_autoforwards_discuss(monkeypatch, tmp_path):
    calls = []

    def fake_record(*args, **kwargs):
        return None

    def fake_sync(*args, **kwargs):
        return None

    def fake_allowed(*args, **kwargs):
        return True

    def fake_read_run_meta(folder):
        return _make_run(tmp_path, phase="DISCUSS", pending=False)

    def fake_patch_run_meta(folder, fn):
        updated = fn({"mission_loop": {}})
        calls.append(("patch", updated.get("mission_loop", {}).get("phase")))

    def fake_mission_dispatch(folder, topic, payload):
        calls.append(("dispatch", topic, payload))

    import agent_lab.mission_loop as ml

    monkeypatch.setattr(ml, "record_autorun_tick", fake_record)
    monkeypatch.setattr(ml, "sync_turn_budget_from_mission", fake_sync)
    monkeypatch.setattr(ml, "_scheduled_autorun_allowed", fake_allowed)
    monkeypatch.setattr(ml, "read_run_meta", fake_read_run_meta)
    monkeypatch.setattr(ml, "patch_run_meta", fake_patch_run_meta)
    monkeypatch.setattr(ml, "_mission_dispatch", fake_mission_dispatch)

    maybe_advance_mission(tmp_path, scheduled=True)


def test_on_verify_result_does_not_double_count(monkeypatch, tmp_path):
    calls = []

    def fake_record_autorun(*args, **kwargs):
        return None

    def fake_sync(*args, **kwargs):
        return None

    def fake_allowed(*args, **kwargs):
        return True

    def fake_read(folder):
        return {
            "mission_loop": {
                "enabled": True,
                "phase": "VERIFY",
                "last_verify": {},
                "plan_gate": {},
                "pending_executions": [],
                "action_repair_counts": {"0": 1},
                "max_repair_per_action": 3,
                "autonomous_segment": {"active": True},
                "discuss_recovery": {},
            },
            "schedule_sandbox": False,
        }

    def fake_patch(folder, fn):
        updated = fn({"mission_loop": {}})
        calls.append(
            {
                "phase": updated.get("mission_loop", {}).get("phase"),
                "repairs": updated.get("mission_loop", {}).get("action_repair_counts"),
            }
        )

    def fake_dispatch(folder, topic, payload):
        calls.append({"dispatch": topic})
        return {}

    def fake_record_last_failure(*args, **kwargs):
        return None

    import agent_lab.mission_loop as ml

    monkeypatch.setattr(ml, "record_autorun_tick", fake_record_autorun)
    monkeypatch.setattr(ml, "sync_turn_budget_from_mission", fake_sync)
    monkeypatch.setattr(ml, "_scheduled_autorun_allowed", fake_allowed)
    monkeypatch.setattr(ml, "read_run_meta", fake_read)
    monkeypatch.setattr(ml, "patch_run_meta", fake_patch)
    monkeypatch.setattr(ml, "_mission_dispatch", fake_dispatch)
    monkeypatch.setattr(ml, "record_last_failure", fake_record_last_failure)

    ml.on_verify_result(tmp_path, action_index=0, verdict="fail", reason="soft-error")

    assert any(entry.get("repairs", {}).get("0") == 1 for entry in calls), calls
