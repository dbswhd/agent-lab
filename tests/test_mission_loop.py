from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.mission_loop import (
    MISSION_NOTEPAD_FILES,
    after_plan_scribe,
    append_wisdom_note,
    build_mission_wisdom_block,
    clear_circuit_breaker,
    enable_mission_loop,
    ensure_mission_notepads,
    evaluate_plan_gate,
    inject_wisdom_into_prompt,
    is_structural_verify_fail,
    list_mission_notepad_summaries,
    maybe_advance_mission,
    mission_notepad_dir,
    on_dry_run_complete,
    on_merge_abort,
    on_merge_confirm,
    on_structural_execution_failure,
    on_verify_result,
    pause_mission_loop,
    resume_mission_loop,
    run_mission_discuss_recovery,
    run_plan_gate,
)
from agent_lab.run_meta import patch_run_meta, read_run_meta
from agent_lab.verified_loop import approve_verified_loop, init_verified_loop, record_proposed_goal


def _good_plan() -> str:
    return """# Plan

## 지금 실행

1. Fix auth module
   - 무엇을: JWT validation in `src/auth.py`
   - 어디서: `src/auth.py`
   - 검증: `make test tests/test_auth.py`
"""


def _bad_plan() -> str:
    return """# Plan

## 지금 실행

1. Fix something
   - 무엇을: fix
   - 어디서: somewhere
   - 검증: ok
"""


@pytest.fixture
def session_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    folder = tmp_path / "sess-mission"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    (folder / "topic.txt").write_text("mission test", encoding="utf-8")
    return folder


def test_evaluate_plan_gate_ok() -> None:
    result = evaluate_plan_gate(_good_plan())
    assert result["status"] == "ok"
    assert result["action_count"] == 1


def test_evaluate_plan_gate_reject() -> None:
    result = evaluate_plan_gate(_bad_plan())
    assert result["status"] == "reject"
    assert result["failures"]


def test_evaluate_plan_gate_mcp_warning_when_allowlist_empty(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "agent_plugins": {
                "claude": {"enabled": []},
                "codex": {"enabled": []},
                "cursor": {"enabled": []},
            },
        },
    )
    plan = """# Plan

## 지금 실행

1. Use Figma MCP
   - 무엇을: fetch design
   - 어디서: `src/ui/`
   - 검증: MCP figma returns frame metadata
"""
    run = read_run_meta(session_folder)
    result = evaluate_plan_gate(plan, run=run)
    assert result.get("mcp_warnings")


def test_enable_and_plan_gate_enqueue(session_folder: Path) -> None:
    enable_mission_loop(session_folder, start_autonomous=False)
    (session_folder / "plan.md").write_text(_good_plan(), encoding="utf-8")
    result = run_plan_gate(session_folder, _good_plan())
    assert result["status"] == "ok"
    run = read_run_meta(session_folder)
    ml = run["mission_loop"]
    assert ml["phase"] == "EXECUTE_QUEUE"
    assert ml["pending_action_indices"] == [1]
    assert ml["current_action_index"] == 1
    assert ml["autonomous_segment"]["active"] is False


def test_open_block_prevents_execute_enqueue(session_folder: Path) -> None:
    from agent_lab.room_objections import append_objection

    enable_mission_loop(session_folder)
    run = read_run_meta(session_folder)
    append_objection(
        run,
        from_agent="codex",
        act="BLOCK",
        body="hold execute",
        human_turn=1,
    )

    def _with_block(run_in: dict) -> dict:
        run_in["objections"] = run["objections"]
        return run_in

    patch_run_meta(session_folder, _with_block)
    result = run_plan_gate(session_folder, _good_plan())
    assert result["status"] == "blocked"
    assert result["http_status"] == 409


def test_plan_gate_reject_then_discuss(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    result = run_plan_gate(session_folder, _bad_plan())
    assert result["status"] == "reject"
    assert result.get("auto_discuss") is True
    run = read_run_meta(session_folder)
    assert run["mission_loop"]["phase"] == "DISCUSS"
    assert run["mission_loop"]["plan_gate"]["momus_round"] == 1


def test_momus_round_cap_circuit_breaker(session_folder: Path) -> None:
    enable_mission_loop(session_folder)

    def _low_cap(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml["plan_gate"]["max_momus_rounds"] = 1
        return run

    patch_run_meta(session_folder, _low_cap)
    result = run_plan_gate(session_folder, _bad_plan())
    assert result.get("circuit_breaker") is True
    run = read_run_meta(session_folder)
    assert run["mission_loop"]["circuit_breaker"] is True
    assert run["mission_loop"]["phase"] == "MISSION_PAUSED"
    assert any(
        i.get("source") == "mission_circuit_break" for i in run.get("human_inbox") or []
    )


def test_verify_pass_advances_queue(session_folder: Path) -> None:
    enable_mission_loop(session_folder)

    def _queue(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "VERIFY",
                "pending_action_indices": [1, 2],
                "current_action_index": 1,
            }
        )
        return run

    patch_run_meta(session_folder, _queue)
    out = on_verify_result(session_folder, action_index=1, verdict="pass")
    assert out["status"] == "pass"
    assert out["pending"] == [2]
    run = read_run_meta(session_folder)
    assert run["mission_loop"]["phase"] == "EXECUTE_QUEUE"
    assert run["mission_loop"]["current_action_index"] == 2


def test_verify_fail_repair_same_index(session_folder: Path) -> None:
    enable_mission_loop(session_folder)

    def _verify(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "VERIFY",
                "pending_action_indices": [1],
                "current_action_index": 1,
            }
        )
        return run

    patch_run_meta(session_folder, _verify)
    out = on_verify_result(session_folder, action_index=1, verdict="fail", reason="tests red")
    assert out["phase"] == "REPAIR"
    assert out["action_index"] == 1
    run = read_run_meta(session_folder)
    assert run["mission_loop"]["current_action_index"] == 1
    assert run["mission_loop"]["action_repair_counts"]["1"] == 1


def test_verify_fail_repair_cap_to_discuss(session_folder: Path) -> None:
    enable_mission_loop(session_folder)

    def _verify(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "VERIFY",
                "pending_action_indices": [1],
                "current_action_index": 1,
                "max_repair_per_action": 2,
                "action_repair_counts": {"1": 1},
            }
        )
        return run

    patch_run_meta(session_folder, _verify)
    out = on_verify_result(
        session_folder,
        action_index=1,
        verdict="fail",
        reason="merge conflict: src/auth.py",
    )
    assert out["repair_cap"] is True
    assert out["structural"] is True
    assert out["phase"] == "DISCUSS"
    run = read_run_meta(session_folder)
    assert run["mission_loop"]["circuit_breaker"] is True
    assert run["mission_loop"]["discuss_recovery"]["pending"] is False


def test_verify_fail_repair_cap_non_structural_schedules_recovery(
    session_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_mission_loop(session_folder, start_autonomous=True)
    (session_folder / "plan.md").write_text(_good_plan(), encoding="utf-8")

    def _queue(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "VERIFY",
                "pending_action_indices": [1],
                "current_action_index": 1,
                "max_repair_per_action": 2,
                "action_repair_counts": {"1": 1},
            }
        )
        return run

    patch_run_meta(session_folder, _queue)

    def _fake_recovery(folder: Path, **kwargs):
        (folder / "plan.md").write_text(_good_plan(), encoding="utf-8")
        return run_plan_gate(folder, _good_plan())

    monkeypatch.setattr(
        "agent_lab.mission_loop.run_mission_discuss_recovery",
        lambda folder, **kw: {
            "status": "discuss_recovery_complete",
            "plan_gate": _fake_recovery(folder),
            "phase": "EXECUTE_QUEUE",
        },
    )

    out = on_verify_result(
        session_folder,
        action_index=1,
        verdict="fail",
        reason="tests still red",
    )
    assert out["repair_cap"] is True
    assert out["structural"] is False
    assert out.get("discuss_recovery") is not None
    run = read_run_meta(session_folder)
    assert run["mission_loop"]["circuit_breaker"] is False
    assert run["mission_loop"]["discuss_recovery"]["pending"] is True


def test_run_mission_discuss_recovery_mock(
    session_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_mission_loop(session_folder)
    (session_folder / "topic.txt").write_text("recovery", encoding="utf-8")
    (session_folder / "plan.md").write_text(_good_plan(), encoding="utf-8")

    def _pending(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "DISCUSS",
                "discuss_recovery": {
                    "pending": True,
                    "reason": "tests red",
                    "action_index": 1,
                },
            }
        )
        return run

    patch_run_meta(session_folder, _pending)

    monkeypatch.setattr(
        "agent_lab.room.continue_room_round",
        lambda *a, **k: ([], _good_plan()),
    )

    out = run_mission_discuss_recovery(session_folder)
    assert out["status"] == "discuss_recovery_complete"
    run = read_run_meta(session_folder)
    assert run["mission_loop"]["discuss_recovery"]["pending"] is False
    assert run["mission_loop"]["phase"] == "EXECUTE_QUEUE"


def test_is_structural_verify_fail() -> None:
    assert is_structural_verify_fail("merge conflict: foo.py") is True
    assert is_structural_verify_fail("tests failed") is False


def test_ensure_mission_notepads(session_folder: Path) -> None:
    created = ensure_mission_notepads(session_folder)
    assert set(created) == set(MISSION_NOTEPAD_FILES)
    base = mission_notepad_dir(session_folder)
    for name in MISSION_NOTEPAD_FILES:
        assert (base / name).is_file()
    run = read_run_meta(session_folder)
    assert len(run["mission_loop"]["wisdom_refs"]) == len(MISSION_NOTEPAD_FILES)


def test_append_wisdom_provenance(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    (session_folder / "plan.md").write_text(_good_plan(), encoding="utf-8")
    (session_folder / "chat.jsonl").write_text('{"role":"user"}\n', encoding="utf-8")
    append_wisdom_note(
        session_folder,
        line="jwt edge case",
        filename="learnings.md",
        action_index=1,
    )
    text = (mission_notepad_dir(session_folder) / "learnings.md").read_text(encoding="utf-8")
    assert "jwt edge case" in text
    assert "chat.jsonl#L" in text
    assert "plan (ref: L" in text


def test_build_mission_wisdom_block(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    append_wisdom_note(session_folder, line="remember jwt edge case")
    run = read_run_meta(session_folder)

    def _discuss(run: dict) -> dict:
        ml = run["mission_loop"]
        ml["phase"] = "DISCUSS"
        run["_session_id"] = session_folder.name
        return run

    patch_run_meta(session_folder, _discuss)
    run = read_run_meta(session_folder)
    run["_session_id"] = session_folder.name
    block = build_mission_wisdom_block(run)
    assert "[Mission wisdom]" in block
    assert "jwt" in block


def test_inject_wisdom_into_prompt(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    append_wisdom_note(session_folder, line="do not skip verify", filename="verification.md")
    run = read_run_meta(session_folder)
    run["_session_id"] = session_folder.name
    run["mission_loop"]["phase"] = "DRY_RUN"
    out = inject_wisdom_into_prompt("execute task", run)
    assert "execute task" in out
    assert "[Mission wisdom]" in out
    assert "verify" in out


def test_list_mission_notepad_summaries(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    append_wisdom_note(session_folder, line="one")
    summaries = list_mission_notepad_summaries(session_folder)
    assert len(summaries) == 3
    assert any(s["file"] == "learnings.md" and s["lines"] >= 1 for s in summaries)


def test_verify_pass_writes_notepads(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    (session_folder / "plan.md").write_text(_good_plan(), encoding="utf-8")

    def _queue(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "VERIFY",
                "pending_action_indices": [1],
                "current_action_index": 1,
            }
        )
        return run

    patch_run_meta(session_folder, _queue)
    on_verify_result(session_folder, action_index=1, verdict="pass")
    base = mission_notepad_dir(session_folder)
    verification = (base / "verification.md").read_text(encoding="utf-8")
    decisions = (base / "decisions.md").read_text(encoding="utf-8")
    assert "verify PASS" in verification
    assert "MISSION_DONE" in decisions


def test_on_structural_execution_failure(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    on_structural_execution_failure(
        session_folder,
        reason="worktree fail closed",
        action_index=1,
    )
    run = read_run_meta(session_folder)
    assert run["mission_loop"]["circuit_breaker"] is True
    assert run["mission_loop"]["phase"] == "MISSION_PAUSED"


def test_after_plan_scribe_runs_gate(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    (session_folder / "plan.md").write_text(_good_plan(), encoding="utf-8")
    result = after_plan_scribe(session_folder, _good_plan())
    assert result is not None
    assert result["status"] == "ok"


def test_verified_approve_enables_mission(session_folder: Path) -> None:
    init_verified_loop(session_folder)
    record_proposed_goal(
        session_folder,
        {"goal": "Ship feature X", "completion_promise": "DONE", "criteria": "tests pass"},
        source="test",
    )

    def _pending(run: dict) -> dict:
        run["verified_loop"]["status"] = "pending_approval"
        return run

    patch_run_meta(session_folder, _pending)
    approve_verified_loop(session_folder)
    run = read_run_meta(session_folder)
    assert run["mission_loop"]["enabled"] is True
    assert run["mission_loop"]["phase"] == "DISCUSS"


def test_clear_circuit_breaker(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    run_plan_gate(session_folder, _bad_plan())

    def _trip(run: dict) -> dict:
        ml = run["mission_loop"]
        ml["circuit_breaker"] = True
        ml["phase"] = "MISSION_PAUSED"
        return run

    patch_run_meta(session_folder, _trip)
    clear_circuit_breaker(session_folder, resume_phase="EXECUTE_QUEUE")
    run = read_run_meta(session_folder)
    assert run["mission_loop"]["circuit_breaker"] is False
    assert run["mission_loop"]["phase"] == "EXECUTE_QUEUE"


def test_maybe_advance_skipped_without_autorun(session_folder: Path) -> None:
    enable_mission_loop(session_folder, start_autonomous=False)

    def _queue(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update({"enabled": True, "phase": "EXECUTE_QUEUE", "current_action_index": 1})
        return run

    patch_run_meta(session_folder, _queue)
    out = maybe_advance_mission(session_folder)
    assert out.get("skipped") is True
    assert out.get("reason") == "autorun_off"


def test_maybe_advance_dry_run_mock(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    enable_mission_loop(session_folder, start_autonomous=True)
    (session_folder / "plan.md").write_text(_good_plan(), encoding="utf-8")

    def _queue(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "EXECUTE_QUEUE",
                "current_action_index": 1,
                "pending_action_indices": [1],
            }
        )
        return run

    patch_run_meta(session_folder, _queue)

    fake_exec = {
        "id": "exec-mock-1",
        "action_index": 1,
        "status": "pending_approval",
    }

    monkeypatch.setattr(
        "agent_lab.plan_execute.run_dry_run",
        lambda *a, **k: fake_exec,
    )

    out = maybe_advance_mission(session_folder)
    assert out.get("status") == "dry_run_complete"
    run = read_run_meta(session_folder)
    assert run["mission_loop"]["phase"] == "MERGE_REVIEW"
    assert run["mission_loop"]["last_execution_id"] == "exec-mock-1"


def test_on_dry_run_complete_sets_merge_review(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    on_dry_run_complete(
        session_folder,
        {"id": "exec-1", "action_index": 1, "status": "pending_approval"},
    )
    run = read_run_meta(session_folder)
    assert run["mission_loop"]["phase"] == "MERGE_REVIEW"


def test_on_merge_confirm_and_abort(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    on_merge_confirm(session_folder, execution_id="exec-1")
    assert read_run_meta(session_folder)["mission_loop"]["phase"] == "VERIFY"
    on_merge_abort(session_folder, execution_id="exec-1")
    assert read_run_meta(session_folder)["mission_loop"]["phase"] == "DISCUSS"


def test_pause_mission_records_last_partial(session_folder: Path) -> None:
    enable_mission_loop(session_folder, start_autonomous=True)

    def _dry_run(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "MERGE_REVIEW",
                "current_action_index": 1,
                "last_execution_id": "exec-pending",
            }
        )
        return run

    patch_run_meta(session_folder, _dry_run)
    out = pause_mission_loop(session_folder, reason="test_stop")
    assert out["status"] == "paused"
    run = read_run_meta(session_folder)
    ml = run["mission_loop"]
    assert ml["phase"] == "MISSION_PAUSED"
    assert ml["pause_reason"] == "test_stop"
    assert ml["last_partial"]["phase"] == "MERGE_REVIEW"
    assert ml["last_partial"]["resume_phase"] == "EXECUTE_QUEUE"
    assert ml["autonomous_segment"]["active"] is False


def test_resume_mission_from_paused(session_folder: Path) -> None:
    enable_mission_loop(session_folder)

    def _paused(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "MISSION_PAUSED",
                "pause_reason": "test",
                "last_partial": {"resume_phase": "EXECUTE_QUEUE"},
            }
        )
        return run

    patch_run_meta(session_folder, _paused)
    out = resume_mission_loop(session_folder)
    assert out["status"] == "resumed"
    run = read_run_meta(session_folder)
    assert run["mission_loop"]["phase"] == "EXECUTE_QUEUE"
    assert run["mission_loop"]["pause_reason"] is None


def test_pause_mission_api(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.server.main import app

    monkeypatch.setattr(
        "app.server.routers.mission_loop.session_folder_or_404",
        lambda _sid: session_folder,
    )
    enable_mission_loop(session_folder)

    def _merge(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update({"enabled": True, "phase": "DRY_RUN", "current_action_index": 1})
        return run

    patch_run_meta(session_folder, _merge)
    client = TestClient(app)
    res = client.post(
        "/api/sessions/sess-mission/mission-loop/pause",
        json={"reason": "api_test"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["mission_loop"]["phase"] == "MISSION_PAUSED"
    assert body["pause"]["status"] == "paused"


def test_cancel_room_run_pauses_mission(
    session_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from app.server.main import app

    monkeypatch.setattr(
        "app.server.deps.session_folder_or_404",
        lambda _sid: session_folder,
    )
    enable_mission_loop(session_folder)

    def _execute(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update({"enabled": True, "phase": "EXECUTE_QUEUE", "current_action_index": 1})
        return run

    patch_run_meta(session_folder, _execute)
    client = TestClient(app)
    res = client.post(
        "/api/room/runs/cancel",
        json={"session_id": "sess-mission"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["mission_pause"]["status"] == "paused"
    assert read_run_meta(session_folder)["mission_loop"]["phase"] == "MISSION_PAUSED"


def test_mission_loop_api(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.server.main import app

    monkeypatch.setattr(
        "app.server.routers.mission_loop.session_folder_or_404",
        lambda _sid: session_folder,
    )
    enable_mission_loop(session_folder)
    client = TestClient(app)
    res = client.get("/api/sessions/sess-mission/mission-loop")
    assert res.status_code == 200
    body = res.json()
    assert body["enabled"] is True
    assert isinstance(body.get("notepads"), list)


def test_discuss_recovery_api(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.server.main import app

    monkeypatch.setattr(
        "app.server.routers.mission_loop.session_folder_or_404",
        lambda _sid: session_folder,
    )
    enable_mission_loop(session_folder)

    def _pending(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "DISCUSS",
                "discuss_recovery": {
                    "pending": True,
                    "reason": "api_test",
                    "action_index": 1,
                },
            }
        )
        return run

    patch_run_meta(session_folder, _pending)
    monkeypatch.setattr(
        "agent_lab.mission_loop.run_mission_discuss_recovery",
        lambda folder, **kw: {
            "status": "discuss_recovery_complete",
            "phase": "EXECUTE_QUEUE",
        },
    )
    client = TestClient(app)
    res = client.post("/api/sessions/sess-mission/mission-loop/discuss-recovery")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body.get("discuss_recovery") is not None
