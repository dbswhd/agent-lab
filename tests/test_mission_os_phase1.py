"""Mission OS Phase 1 — gateway, scheduler, templates, daemon API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import pytest
from fastapi.testclient import TestClient

from agent_lab.gateway.config import gateway_config_path, load_gateway_config, save_gateway_config
from agent_lab.gateway.outbound import deliver_outbound_event
from agent_lab.mission_scheduler import cron_matches, schedule_due, scheduler_tick
from agent_lab.mission_templates import (
    init_plan_workflow_from_template,
    sign_template_pre_approval,
    templates_root,
)
from agent_lab.plan_workflow import get_plan_workflow
from agent_lab.run_meta import patch_run_meta, read_run_meta
from app.server.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def sessions_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import agent_lab.mission_scheduler as sched_mod
    import agent_lab.mission_templates as tmpl_mod
    import agent_lab.session as session_mod
    import app.server.deps as deps_mod

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(tmpl_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(sched_mod, "SESSIONS_DIR", tmp_path)
    templates_root(tmp_path).mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def gateway_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "gateway.toml"
    monkeypatch.setenv("AGENT_LAB_GATEWAY_CONFIG", str(path))
    return path


def test_cron_matches_weekday_morning() -> None:
    when = datetime(2026, 6, 15, 7, 30, tzinfo=timezone.utc)  # Mon
    assert cron_matches("30 7 * * 1-5", when) is True
    assert cron_matches("30 8 * * 1-5", when) is False


def test_schedule_due_requires_pre_approve() -> None:
    entry = {
        "id": "s1",
        "cron": "30 7 * * *",
        "enabled": True,
    }
    when = datetime(2026, 6, 15, 7, 30, tzinfo=timezone.utc)
    assert schedule_due(entry, now=when) is False
    entry["pre_approved_at"] = "2026-06-14T00:00:00+00:00"
    assert schedule_due(entry, now=when) is True


def test_gateway_config_roundtrip(gateway_config: Path) -> None:
    save_gateway_config(
        {
            "outbound": {
                "enabled": True,
                "urls": ["https://example.com/hook"],
                "secret": "sekrit",
                "events": ["schedule_tick"],
            }
        }
    )
    cfg = load_gateway_config()
    assert cfg["outbound"]["enabled"] is True
    assert cfg["outbound"]["urls"] == ["https://example.com/hook"]
    assert gateway_config_path().is_file()


def test_outbound_delivery_local_server(gateway_config: Path) -> None:
    received: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            received.append(json.loads(body.decode("utf-8")))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_args) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        save_gateway_config(
            {
                "outbound": {
                    "enabled": True,
                    "urls": [f"http://127.0.0.1:{port}/hook"],
                    "events": ["schedule_tick"],
                }
            }
        )
        result = deliver_outbound_event("schedule_tick", {"session_id": "x"})
        assert result["ok"] is True
        assert len(received) == 1
        assert received[0]["event"] == "schedule_tick"
    finally:
        server.shutdown()


def test_template_fast_path_approve(sessions_env: Path) -> None:
    tid = "demo"
    tdir = templates_root(sessions_env) / tid
    tdir.mkdir(parents=True)
    plan = "# Demo\n\n1. Step\n   - 검증: `make test-fast`\n"
    (tdir / "plan.md").write_text(plan, encoding="utf-8")
    (tdir / "topic.txt").write_text("demo\n", encoding="utf-8")
    sign_template_pre_approval(tdir)

    sess = sessions_env / "sess-1"
    sess.mkdir()
    (sess / "run.json").write_text("{}", encoding="utf-8")

    result = init_plan_workflow_from_template(sess, tid, sessions_dir=sessions_env)
    assert result.get("fast_path") is True
    pw = get_plan_workflow(read_run_meta(sess))
    assert pw["phase"] == "APPROVED"
    assert pw["approved_by"] == f"template:{tid}"


def test_template_hash_mismatch_falls_back_to_fsm(sessions_env: Path) -> None:
    tid = "drift"
    tdir = templates_root(sessions_env) / tid
    tdir.mkdir(parents=True)
    (tdir / "plan.md").write_text("# A\n", encoding="utf-8")
    (tdir / "topic.txt").write_text("a\n", encoding="utf-8")
    (tdir / "template_meta.json").write_text(
        json.dumps({"hash": "deadbeef"}),
        encoding="utf-8",
    )
    sess = sessions_env / "sess-2"
    sess.mkdir()
    (sess / "run.json").write_text("{}", encoding="utf-8")
    result = init_plan_workflow_from_template(sess, tid, sessions_dir=sessions_env)
    assert result.get("fast_path") is False
    assert get_plan_workflow(read_run_meta(sess))["phase"] == "CLARIFY"


def test_mission_os_api(client: TestClient, sessions_env: Path, gateway_config: Path) -> None:
    folder = sessions_env / "api-sess"
    folder.mkdir()
    (folder / "topic.txt").write_text("api\n", encoding="utf-8")
    (folder / "run.json").write_text("{}", encoding="utf-8")

    r = client.get("/api/health/daemon")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = client.patch(
        "/api/settings/gateway",
        json={"outbound": {"enabled": True, "urls": [], "events": ["test_ping"]}},
    )
    assert r.status_code == 200
    assert r.json()["outbound"]["enabled"] is True

    r = client.patch(
        f"/api/sessions/{folder.name}/schedules",
        json={
            "schedules": [
                {
                    "id": "sched-1",
                    "cron": "0 9 * * *",
                    "tz": "UTC",
                    "gate_profile": "assistant",
                    "sandbox": True,
                }
            ]
        },
    )
    assert r.status_code == 200
    assert len(r.json()["schedules"]) == 1

    r = client.post(f"/api/sessions/{folder.name}/schedules/sched-1/approve")
    assert r.status_code == 200
    run = read_run_meta(folder)
    assert run["schedules"][0]["pre_approved_by"] == "human"


def test_scheduler_tick_records_run(sessions_env: Path, gateway_config: Path) -> None:
    folder = sessions_env / "sched-sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")

    def _set(run: dict) -> dict:
        run["schedules"] = [
            {
                "id": "s1",
                "cron": "30 7 * * *",
                "tz": "UTC",
                "enabled": True,
                "pre_approved_at": "2026-06-01T00:00:00+00:00",
                "pre_approved_by": "human",
                "gate_profile": "dev",
            }
        ]
        return run

    patch_run_meta(folder, _set)
    save_gateway_config({"outbound": {"enabled": False}})
    result = scheduler_tick(sessions_dir=sessions_env, force=True)
    assert result["ok"] is True
    run = read_run_meta(folder)
    assert run["schedules"][0].get("last_run_date")
    assert run["schedules"][0].get("last_run_status") == "ok"
    assert run.get("gate_profile") == "dev"


def test_scheduler_applies_template_assistant(sessions_env: Path, gateway_config: Path) -> None:
    tid = "cron-demo"
    tdir = templates_root(sessions_env) / tid
    tdir.mkdir(parents=True)
    plan = "# Cron\n\n1. Step\n   - 검증: `make test-fast`\n"
    (tdir / "plan.md").write_text(plan, encoding="utf-8")
    (tdir / "topic.txt").write_text("cron\n", encoding="utf-8")
    sign_template_pre_approval(tdir)

    folder = sessions_env / "sched-tmpl"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    patch_run_meta(
        folder,
        lambda run: {
            **run,
            "schedules": [
                {
                    "id": "s-tmpl",
                    "cron": "0 9 * * *",
                    "tz": "UTC",
                    "enabled": True,
                    "pre_approved_at": "2026-06-01T00:00:00+00:00",
                    "pre_approved_by": "human",
                    "gate_profile": "assistant",
                    "template_id": tid,
                    "sandbox": True,
                }
            ],
        },
    )
    save_gateway_config({"outbound": {"enabled": False}})
    from agent_lab.mission_scheduler import run_schedule_entry

    result = run_schedule_entry(
        folder.name, read_run_meta(folder)["schedules"][0], sessions_dir=sessions_env, force=True
    )
    assert result["ok"] is True
    assert result["mode"] == "assistant_sandbox_tick"
    tick = result.get("sandbox_tick") or {}
    assert tick.get("ok") is True
    assert tick.get("read_only") is True
    assert "mission_loop" in tick
    pw = get_plan_workflow(read_run_meta(folder))
    assert pw["phase"] == "APPROVED"
    assert read_run_meta(folder).get("schedule_sandbox") is True


def test_scheduler_templateless_sandbox_runs_conductor_tick(sessions_env: Path, gateway_config: Path) -> None:
    """Template-less assistant schedule still runs sandbox mission conductor."""
    from agent_lab.mission_loop import enable_mission_loop
    from agent_lab.mission_scheduler import run_schedule_entry

    folder = sessions_env / "sched-no-tmpl-sandbox"
    folder.mkdir()
    (folder / "plan.md").write_text(
        "# Plan\n\n1. Step\n   - 무엇을: fix\n   - 어디서: src\n   - 검증: `make test`\n",
        encoding="utf-8",
    )
    (folder / "run.json").write_text("{}", encoding="utf-8")
    enable_mission_loop(folder, start_autonomous=False)
    patch_run_meta(
        folder,
        lambda run: {
            **run,
            "schedules": [
                {
                    "id": "s-no-tmpl",
                    "cron": "0 9 * * *",
                    "tz": "UTC",
                    "enabled": True,
                    "pre_approved_at": "2026-06-01T00:00:00+00:00",
                    "pre_approved_by": "human",
                    "gate_profile": "assistant",
                    "sandbox": True,
                }
            ],
        },
    )
    save_gateway_config({"outbound": {"enabled": False}})

    result = run_schedule_entry(
        folder.name,
        read_run_meta(folder)["schedules"][0],
        sessions_dir=sessions_env,
        force=True,
    )
    assert result["ok"] is True
    assert result["mode"] == "assistant_sandbox_tick"
    tick = result.get("sandbox_tick") or {}
    assert tick.get("ok") is True
    assert tick.get("read_only") is True
    assert read_run_meta(folder).get("schedule_sandbox") is True


def test_scheduler_templateless_non_sandbox_runs_mission_tick(
    sessions_env: Path, gateway_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Template-less non-sandbox schedule advances mission_loop conductor."""
    from agent_lab.mission_loop import enable_mission_loop
    from agent_lab.mission_scheduler import run_schedule_entry

    folder = sessions_env / "sched-no-tmpl-live"
    folder.mkdir()
    plan = """# Plan

## 지금 실행

1. Fix auth module
   - 무엇을: JWT validation in `src/auth.py`
   - 어디서: `src/auth.py`
   - 검증: `make test tests/test_auth.py`
"""
    (folder / "plan.md").write_text(plan, encoding="utf-8")
    (folder / "run.json").write_text("{}", encoding="utf-8")
    enable_mission_loop(folder, start_autonomous=True)

    def _queue(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "EXECUTE_QUEUE",
                "current_action_index": 1,
                "pending_action_indices": [1],
                "autonomous_segment": {"active": True},
            }
        )
        run["schedules"] = [
            {
                "id": "s-no-tmpl-live",
                "cron": "0 9 * * *",
                "tz": "UTC",
                "enabled": True,
                "pre_approved_at": "2026-06-01T00:00:00+00:00",
                "pre_approved_by": "human",
                "gate_profile": "assistant",
                "sandbox": False,
            }
        ]
        return run

    patch_run_meta(folder, _queue)
    save_gateway_config({"outbound": {"enabled": False}})

    fake_exec = {
        "id": "exec-no-tmpl",
        "action_index": 1,
        "status": "pending_approval",
    }
    monkeypatch.setattr(
        "agent_lab.plan_execute.run_dry_run",
        lambda *a, **k: fake_exec,
    )

    result = run_schedule_entry(
        folder.name,
        read_run_meta(folder)["schedules"][0],
        sessions_dir=sessions_env,
        force=True,
    )
    assert result["ok"] is True
    assert result["mode"] == "assistant_mission_tick"
    tick = result.get("sandbox_tick") or {}
    assert tick.get("sandbox") is False
    assert tick.get("mission_loop", {}).get("status") == "dry_run_complete"
    run = read_run_meta(folder)
    assert run["mission_loop"]["phase"] == "MERGE_REVIEW"


def test_scheduled_mission_tick_sandbox_skips_execute_queue(sessions_env: Path) -> None:
    folder = sessions_env / "sandbox-exec"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    (folder / "plan.md").write_text(
        "# Plan\n\n1. Step\n   - 무엇을: fix\n   - 어디서: src\n   - 검증: `make test`\n",
        encoding="utf-8",
    )

    def _patch(run: dict) -> dict:
        run["schedule_sandbox"] = True
        run["mission_loop"] = {
            "enabled": True,
            "phase": "EXECUTE_QUEUE",
            "current_action_index": 1,
            "pending_action_indices": [1],
            "autonomous_segment": {"active": True},
        }
        return run

    patch_run_meta(folder, _patch)

    from agent_lab.mission_tick import run_scheduled_mission_tick

    result = run_scheduled_mission_tick(folder, schedule_id="s-sandbox", sandbox=True)
    assert result["ok"] is True
    ml = result["mission_loop"]
    assert ml.get("reason") == "schedule_sandbox_read_only"
    assert ml.get("phase") == "EXECUTE_QUEUE"


def test_scheduled_mission_tick_non_sandbox_advances_execute(
    sessions_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_lab.mission_loop import enable_mission_loop
    from agent_lab.mission_tick import run_scheduled_mission_tick

    folder = sessions_env / "live-exec"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    plan = """# Plan

## 지금 실행

1. Fix auth module
   - 무엇을: JWT validation in `src/auth.py`
   - 어디서: `src/auth.py`
   - 검증: `make test tests/test_auth.py`
"""
    (folder / "plan.md").write_text(plan, encoding="utf-8")
    enable_mission_loop(folder, start_autonomous=True)

    def _queue(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "EXECUTE_QUEUE",
                "current_action_index": 1,
                "pending_action_indices": [1],
                "autonomous_segment": {"active": True},
            }
        )
        return run

    patch_run_meta(folder, _queue)

    fake_exec = {
        "id": "exec-sched-1",
        "action_index": 1,
        "status": "pending_approval",
    }
    monkeypatch.setattr(
        "agent_lab.plan_execute.run_dry_run",
        lambda *a, **k: fake_exec,
    )

    result = run_scheduled_mission_tick(folder, schedule_id="s-live", sandbox=False)
    assert result["ok"] is True
    assert result["sandbox"] is False
    assert result["mission_loop"].get("status") == "dry_run_complete"
    run = read_run_meta(folder)
    assert run["mission_loop"]["phase"] == "MERGE_REVIEW"


def test_scheduler_non_sandbox_runs_mission_tick(
    sessions_env: Path, gateway_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tid = "cron-live"
    tdir = templates_root(sessions_env) / tid
    tdir.mkdir(parents=True)
    plan = """# Cron live

## 지금 실행

1. Fix auth module
   - 무엇을: JWT validation in `src/auth.py`
   - 어디서: `src/auth.py`
   - 검증: `make test tests/test_auth.py`
"""
    (tdir / "plan.md").write_text(plan, encoding="utf-8")
    (tdir / "topic.txt").write_text("cron-live\n", encoding="utf-8")
    sign_template_pre_approval(tdir)

    folder = sessions_env / "sched-live"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    patch_run_meta(
        folder,
        lambda run: {
            **run,
            "schedules": [
                {
                    "id": "s-live",
                    "cron": "0 9 * * *",
                    "tz": "UTC",
                    "enabled": True,
                    "pre_approved_at": "2026-06-01T00:00:00+00:00",
                    "pre_approved_by": "human",
                    "gate_profile": "assistant",
                    "template_id": tid,
                    "sandbox": False,
                }
            ],
        },
    )
    save_gateway_config({"outbound": {"enabled": False}})

    fake_exec = {
        "id": "exec-sched-live",
        "action_index": 1,
        "status": "pending_approval",
    }
    monkeypatch.setattr(
        "agent_lab.plan_execute.run_dry_run",
        lambda *a, **k: fake_exec,
    )

    from agent_lab.mission_scheduler import run_schedule_entry

    result = run_schedule_entry(
        folder.name,
        read_run_meta(folder)["schedules"][0],
        sessions_dir=sessions_env,
        force=True,
    )
    assert result["ok"] is True
    assert result["mode"] == "assistant_mission_tick"
    tick = result.get("sandbox_tick") or {}
    assert tick.get("sandbox") is False
    assert tick.get("mission_loop", {}).get("status") == "dry_run_complete"


def test_scheduled_autorun_without_active_segment(sessions_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scheduled assistant tick advances execute even after dry-run cleared autorun."""
    from agent_lab.mission_loop import enable_mission_loop
    from agent_lab.mission_tick import run_scheduled_mission_tick

    folder = sessions_env / "sched-autorun-off"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    enable_mission_loop(folder, start_autonomous=False)

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
    monkeypatch.setattr(
        "agent_lab.plan_execute.run_dry_run",
        lambda *a, **k: {
            "id": "exec-no-seg",
            "action_index": 1,
            "status": "pending_approval",
        },
    )

    result = run_scheduled_mission_tick(folder, schedule_id="s-no-seg", sandbox=False)
    assert result["ok"] is True
    assert result["mission_loop"].get("status") == "dry_run_complete"


def test_scheduled_conductor_auto_merge_and_next_action(sessions_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.mission_loop import enable_mission_loop, on_verify_result
    from agent_lab.mission_tick import run_scheduled_mission_tick
    from agent_lab.trust_budget import set_trust_budget

    folder = sessions_env / "conductor-chain"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    enable_mission_loop(folder, start_autonomous=False)
    set_trust_budget(
        folder,
        {"auto_merge_remaining": 2, "classifier_allow": ["docs_only"]},
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
                "pending_action_indices": [1, 2],
                "last_execution_id": "exec-a1",
                "autonomous_segment": {"active": False},
            }
        )
        return run

    patch_run_meta(folder, _merge_review)

    dry_run_actions: list[int] = []
    merge_calls: list[str] = []

    def _fake_dry_run(folder_arg, action_index, **kwargs):
        dry_run_actions.append(int(action_index))
        exec_row = {
            "id": f"exec-a{action_index}",
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
        merge_calls.append(execution_id)
        run = read_run_meta(folder_arg)
        target = next(
            row for row in (run.get("executions") or []) if isinstance(row, dict) and row.get("id") == execution_id
        )
        idx = int(target.get("action_index") or 0)
        on_verify_result(folder_arg, action_index=idx, verdict="pass")

        def _mark_merged(run: dict) -> dict:
            for row in run.get("executions") or []:
                if isinstance(row, dict) and row.get("id") == execution_id:
                    row["status"] = "merged"
            return run

        patch_run_meta(folder_arg, _mark_merged)
        return {"auto_merge": {"eligible": True}, "execution": {"id": execution_id}}

    monkeypatch.setattr("agent_lab.plan_execute.run_dry_run", _fake_dry_run)
    monkeypatch.setattr("agent_lab.auto_merge.resolve_auto_merge", _fake_auto_merge)

    result = run_scheduled_mission_tick(folder, schedule_id="s-chain", sandbox=False)
    assert result["ok"] is True
    ml = result["mission_loop"]
    assert len(ml.get("conductor_steps") or []) >= 3
    assert dry_run_actions == [2]
    assert merge_calls == ["exec-a1", "exec-a2"]
    run = read_run_meta(folder)
    assert run["mission_loop"]["phase"] == "MISSION_DONE"
    assert run["mission_loop"]["pending_action_indices"] == []


def test_maybe_advance_scheduled_merge_review(sessions_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.mission_loop import enable_mission_loop, maybe_advance_mission, on_verify_result
    from agent_lab.trust_budget import set_trust_budget

    folder = sessions_env / "merge-review"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    enable_mission_loop(folder)
    set_trust_budget(
        folder,
        {"auto_merge_remaining": 1, "classifier_allow": ["docs_only"]},
    )

    def _state(run: dict) -> dict:
        run["gate_profile"] = "assistant"
        run["executions"] = [
            {
                "id": "exec-mr",
                "status": "pending_approval",
                "action_index": 1,
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
                "last_execution_id": "exec-mr",
            }
        )
        return run

    patch_run_meta(folder, _state)

    monkeypatch.setattr(
        "agent_lab.auto_merge.resolve_auto_merge",
        lambda folder_arg, *, execution_id: (
            on_verify_result(
                folder_arg,
                action_index=int(
                    next(
                        row["action_index"]
                        for row in read_run_meta(folder_arg).get("executions") or []
                        if isinstance(row, dict) and row.get("id") == execution_id
                    )
                ),
                verdict="pass",
            ),
            {"auto_merge": {"eligible": True}, "execution": {"id": execution_id}},
        )[1],
    )

    out = maybe_advance_mission(folder, scheduled=True)
    assert out.get("status") == "auto_merge_complete"
    assert read_run_meta(folder)["mission_loop"]["phase"] == "MISSION_DONE"


def test_scheduler_hash_mismatch_blocked(sessions_env: Path, gateway_config: Path) -> None:
    tid = "drift-cron"
    tdir = templates_root(sessions_env) / tid
    tdir.mkdir(parents=True)
    (tdir / "plan.md").write_text("# Drift\n", encoding="utf-8")
    (tdir / "template_meta.json").write_text('{"hash":"deadbeef"}\n', encoding="utf-8")

    folder = sessions_env / "sched-blocked"
    folder.mkdir()
    entry = {
        "id": "s-block",
        "cron": "0 9 * * *",
        "tz": "UTC",
        "enabled": True,
        "pre_approved_at": "2026-06-01T00:00:00+00:00",
        "pre_approved_by": "human",
        "gate_profile": "assistant",
        "template_id": tid,
    }
    patch_run_meta(folder, lambda run: {**run, "schedules": [entry]})
    save_gateway_config({"outbound": {"enabled": False}})

    from agent_lab.mission_scheduler import run_schedule_entry

    result = run_schedule_entry(folder.name, entry, sessions_dir=sessions_env, force=True)
    assert result["ok"] is False
    assert result["reason"] == "hash_mismatch"
    run = read_run_meta(folder)
    assert run["schedules"][0].get("last_run_status") == "blocked"
    assert not run["schedules"][0].get("last_run_date")


def test_schedule_sandbox_blocks_execute(sessions_env: Path) -> None:
    folder = sessions_env / "sandbox-sess"
    folder.mkdir()
    patch_run_meta(folder, lambda run: {**run, "schedule_sandbox": True})
    from agent_lab.runtime.policy import PolicyEngine

    result = PolicyEngine.check_execute_allowed(read_run_meta(folder), 0)
    assert result.allowed is False
    assert result.source == "schedule_sandbox"
