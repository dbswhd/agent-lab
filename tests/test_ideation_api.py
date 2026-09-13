"""RI-07 — session creation opt-in and the GET/PATCH ideation API.

The completion path this file pins, end to end:

    세션 생성 → 상태 GET → 후보 선택 PATCH → 새로고침 후 복원
    → 같은 요청 재전송 시 중복 없음 → 오래된 revision은 409
    → 선택이 실행 승인으로 바뀌지 않음
"""

from __future__ import annotations

from pathlib import Path

import asyncio

import pytest

from agent_lab import ideation

pytest.importorskip("fastapi")


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    import agent_lab.session as session_mod
    import app.server.deps as deps_mod

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)

    from app.server.main import app

    return TestClient(app)


def _make_session(tmp_path: Path, *, with_ideation: bool = True, stage: str = ideation.STAGE_EXPLORE):
    """A session on disk, seeded the way the create endpoint seeds one."""
    from agent_lab.run.meta import write_run_meta
    from agent_lab.run.state import RunState

    folder = tmp_path / f"sess-{'idea' if with_ideation else 'legacy'}-{stage}"
    folder.mkdir(exist_ok=True)
    (folder / "topic.txt").write_text("막연한 개념\n", encoding="utf-8")
    run = RunState.from_memory({"topic": "막연한 개념"})
    if with_ideation:
        payload = ideation.new_ideation(original_concept="막연한 개념")
        payload["stage"] = stage
        payload["options"] = [
            {"id": "opt-0-cursor", "title": "A안"},
            {"id": "opt-0-codex", "title": "B안"},
            {"id": "opt-0-claude", "title": "C안"},
        ]
        ideation.start_ideation(run, payload)
    write_run_meta(folder, dict(run))
    return folder


def _patch(client, sid, **body):
    return client.patch(f"/api/sessions/{sid}/ideation", json=body)


# --- opt-in --------------------------------------------------------------


def test_opt_in_seeds_ideation_on_a_new_session(client, tmp_path, monkeypatch):
    """`ideation=true` on creation is the only way in."""
    from agent_lab.run.meta import read_run_meta

    res = client.post("/api/room/runs", data={"topic": "막연한 개념", "ideation": "true"})
    assert res.status_code == 200
    res.read()

    folders = [p for p in tmp_path.iterdir() if p.is_dir() and (p / "run.json").is_file()]
    assert len(folders) == 1
    state = ideation.read_ideation(read_run_meta(folders[0]))
    assert state is not None
    assert state["stage"] == ideation.STAGE_EXPLORE
    assert state["brief"]["original_concept"] == "막연한 개념"
    # The create call also runs the first turn, so the seeded state has already
    # recorded that batch's candidates — seeding and the round agree.
    assert state["revision"] >= 1
    assert state["options"]
    assert state["selection"] is None


def test_creation_without_opt_in_stays_on_the_execute_lane(client, tmp_path):
    from agent_lab.run.meta import read_run_meta

    res = client.post("/api/room/runs", data={"topic": "실행할 작업"})
    assert res.status_code == 200
    res.read()

    folders = [p for p in tmp_path.iterdir() if p.is_dir() and (p / "run.json").is_file()]
    assert len(folders) == 1
    run = read_run_meta(folders[0])
    assert "ideation" not in run
    assert ideation.is_ideation_session(run) is False


def test_opt_in_does_not_convert_an_existing_session(client, tmp_path):
    """Migrating a live execute-lane session is exactly what §4.1 rules out."""
    from agent_lab.run.meta import read_run_meta

    folder = _make_session(tmp_path, with_ideation=False)
    res = client.post(
        "/api/room/runs",
        data={"topic": "이어서", "session_id": folder.name, "ideation": "true"},
    )
    assert res.status_code == 400
    assert "new sessions only" in res.json()["detail"]
    assert "ideation" not in read_run_meta(folder)


def test_a_direct_call_without_the_flag_does_not_opt_in(tmp_path, monkeypatch):
    """`Form(False)` arrives as a truthy FieldInfo on a direct function call.

    Several tests call `create_room_run(...)` as a function and pass only the
    params they care about, so the default must not opt a session in — nor
    trip the "existing session" rejection.
    """
    import agent_lab.session as session_mod
    import app.server.deps as deps_mod
    import app.server.routers.room as room_router
    from agent_lab.run.meta import read_run_meta

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)
    # provider readiness is env-dependent and not what this test is about
    monkeypatch.setattr(room_router, "_agents_not_ready", lambda agent_list: [])

    folder = _make_session(tmp_path, with_ideation=False)

    class _Request:
        async def is_disconnected(self):
            return True

    response = asyncio.run(
        room_router.create_room_run(
            _Request(),
            topic="이어서",
            agents='["cursor"]',
            synthesize=False,
            synthesize_only=False,
            mode="discuss",
            session_id=folder.name,
            permissions="{}",
            skill_intent=None,
            agent_rounds=1,
            request_id=None,
            review_mode=False,
            consensus_mode=False,
            efficiency_mode=False,
            turn_profile="discuss",
            preset="",
            role_policy="",
            research_mode=False,
            workspace_id="agent-lab",
            workspace_path=None,
            session_template="general",
            agent_capabilities="{}",
            agent_thread_bindings="{}",
            room_models="",
            files=[],
        )
    )
    assert response is not None
    assert "ideation" not in read_run_meta(folder)


# --- GET -----------------------------------------------------------------


def test_get_returns_the_state(client, tmp_path):
    folder = _make_session(tmp_path)
    res = client.get(f"/api/sessions/{folder.name}/ideation")

    assert res.status_code == 200
    body = res.json()
    assert body["stage"] == ideation.STAGE_EXPLORE
    assert body["revision"] == 0
    assert body["plan_stale"] is False
    assert [o["id"] for o in body["ideation"]["options"]] == [
        "opt-0-cursor",
        "opt-0-codex",
        "opt-0-claude",
    ]


def test_get_is_side_effect_free(client, tmp_path):
    """`GET /api/sessions/{id}` syncs the plan pipeline; this one must not."""
    folder = _make_session(tmp_path)
    before = (folder / "run.json").read_text(encoding="utf-8")

    for _ in range(3):
        assert client.get(f"/api/sessions/{folder.name}/ideation").status_code == 200

    assert (folder / "run.json").read_text(encoding="utf-8") == before
    assert not (folder / "plan.md").exists()
    assert sorted(p.name for p in folder.iterdir()) == ["run.json", "topic.txt"]


def test_get_on_a_non_ideation_session_is_404(client, tmp_path):
    folder = _make_session(tmp_path, with_ideation=False)
    assert client.get(f"/api/sessions/{folder.name}/ideation").status_code == 404


# --- select / combine / reject / reset ------------------------------------


def test_select_records_the_choice_and_moves_to_shape(client, tmp_path):
    folder = _make_session(tmp_path)
    res = _patch(client, folder.name, command="select", option_id="opt-0-codex", reason="제약에 맞음")

    assert res.status_code == 200
    body = res.json()
    assert body["applied"] is True
    assert body["idempotent"] is False
    assert body["stage"] == ideation.STAGE_SHAPE
    assert body["revision"] == 1
    assert body["ideation"]["selection"]["option_id"] == "opt-0-codex"
    assert body["ideation"]["selection"]["reason"] == "제약에 맞음"


def test_combine_keeps_parent_links(client, tmp_path):
    folder = _make_session(tmp_path)
    res = _patch(
        client,
        folder.name,
        command="combine",
        parent_ids=["opt-0-cursor", "opt-0-claude"],
        new_id="opt-ac",
        reason="둘을 합침",
    )

    assert res.status_code == 200
    selection = res.json()["ideation"]["selection"]
    assert selection["option_id"] == "opt-ac"
    assert selection["parent_ids"] == ["opt-0-cursor", "opt-0-claude"]


def test_reject_and_reset_keep_the_decision_record(client, tmp_path):
    folder = _make_session(tmp_path)
    _patch(client, folder.name, command="select", option_id="opt-0-cursor")
    _patch(client, folder.name, command="reject", option_id="opt-0-claude", reason="플랫폼이 안 맞음")
    res = _patch(client, folder.name, command="reset", reason="다른 방향도 보고 싶다")

    assert res.status_code == 200
    body = res.json()["ideation"]
    assert body["stage"] == ideation.STAGE_EXPLORE
    assert body["selection"] is None
    assert [d["kind"] for d in body["decisions"]] == ["select", "reject", "reopen"]
    assert ideation.rejected_option_ids(body) == ["opt-0-claude"]


def test_unknown_option_is_409_not_a_crash(client, tmp_path):
    folder = _make_session(tmp_path)
    assert _patch(client, folder.name, command="select", option_id="opt-nope").status_code == 409


def test_malformed_command_is_422(client, tmp_path):
    folder = _make_session(tmp_path)
    assert _patch(client, folder.name, command="select").status_code == 422
    assert _patch(client, folder.name, command="combine").status_code == 422
    assert _patch(client, folder.name, command="explode").status_code == 422


# --- idempotency ---------------------------------------------------------


def test_resending_the_same_request_id_changes_nothing(client, tmp_path):
    folder = _make_session(tmp_path)
    first = _patch(client, folder.name, command="select", option_id="opt-0-codex", request_id="req-1")
    assert first.json()["applied"] is True
    assert first.json()["revision"] == 1

    second = _patch(client, folder.name, command="select", option_id="opt-0-codex", request_id="req-1")
    assert second.status_code == 200
    assert second.json()["applied"] is False
    assert second.json()["idempotent"] is True
    assert second.json()["revision"] == 1

    state = client.get(f"/api/sessions/{folder.name}/ideation").json()["ideation"]
    assert len([d for d in state["decisions"] if d["kind"] == "select"]) == 1


def test_reselecting_the_same_option_is_a_duplicate_not_a_conflict(client, tmp_path):
    """Even without a request_id, and even from a stale client view."""
    folder = _make_session(tmp_path)
    _patch(client, folder.name, command="select", option_id="opt-0-codex", expected_revision=0)

    again = _patch(client, folder.name, command="select", option_id="opt-0-codex", expected_revision=0)
    assert again.status_code == 200
    assert again.json()["applied"] is False
    assert again.json()["revision"] == 1


def test_a_different_choice_from_the_same_stale_view_is_a_conflict(client, tmp_path):
    folder = _make_session(tmp_path)
    _patch(client, folder.name, command="select", option_id="opt-0-codex", expected_revision=0)

    res = _patch(client, folder.name, command="select", option_id="opt-0-cursor", expected_revision=0)
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail["code"] == "stale_revision"
    assert detail["expected_revision"] == 0
    assert detail["current_revision"] == 1

    state = client.get(f"/api/sessions/{folder.name}/ideation").json()
    assert state["ideation"]["selection"]["option_id"] == "opt-0-codex"
    assert state["revision"] == 1


def test_repeated_reject_and_reset_do_not_pile_up_decisions(client, tmp_path):
    folder = _make_session(tmp_path)
    for _ in range(3):
        _patch(client, folder.name, command="reject", option_id="opt-0-claude")
    for _ in range(3):
        _patch(client, folder.name, command="reset")

    state = client.get(f"/api/sessions/{folder.name}/ideation").json()["ideation"]
    assert [d["kind"] for d in state["decisions"]] == ["reject"]
    assert state["revision"] == 1


# --- persistence ---------------------------------------------------------


def test_state_is_restored_after_a_refresh(client, tmp_path):
    folder = _make_session(tmp_path)
    _patch(client, folder.name, command="select", option_id="opt-0-claude", reason="이유")
    _patch(client, folder.name, command="reject", option_id="opt-0-cursor")

    # a "refresh" is a fresh read straight off disk
    from agent_lab.run.meta import read_run_meta

    on_disk = ideation.read_ideation(read_run_meta(folder))
    via_api = client.get(f"/api/sessions/{folder.name}/ideation").json()["ideation"]

    assert on_disk == via_api
    assert via_api["selection"]["option_id"] == "opt-0-claude"
    assert via_api["selection"]["reason"] == "이유"
    assert ideation.rejected_option_ids(via_api) == ["opt-0-cursor"]


def test_a_running_turn_is_refused_rather_than_overwritten(client, tmp_path, monkeypatch):
    """Turn-end replay would silently clobber a write landing mid-turn."""
    import app.server.routers.sessions as sessions_mod

    folder = _make_session(tmp_path)
    monkeypatch.setattr(
        "agent_lab.run.control.run_lock_status",
        lambda: {"locked": True, "session_id": folder.name},
    )
    assert sessions_mod  # the router imports run_lock_status lazily

    res = _patch(client, folder.name, command="select", option_id="opt-0-codex")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "busy"
    assert client.get(f"/api/sessions/{folder.name}/ideation").json()["revision"] == 0


def test_a_run_on_another_session_does_not_block_this_one(client, tmp_path, monkeypatch):
    folder = _make_session(tmp_path)
    monkeypatch.setattr(
        "agent_lab.run.control.run_lock_status",
        lambda: {"locked": True, "session_id": "some-other-session"},
    )
    assert _patch(client, folder.name, command="select", option_id="opt-0-codex").status_code == 200


# --- the selection is not an approval ------------------------------------


def test_selecting_does_not_approve_execution(client, tmp_path):
    from agent_lab.plan.workflow import PlanWorkflowNotApproved, ensure_plan_workflow_approved
    from agent_lab.run.meta import read_run_meta

    folder = _make_session(tmp_path)
    _patch(client, folder.name, command="select", option_id="opt-0-codex")

    run = read_run_meta(folder)
    assert "plan_workflow" not in run
    assert "mission_loop" not in run
    assert "goal_loop" not in run
    assert not run.get("executions")

    with pytest.raises(PlanWorkflowNotApproved) as excinfo:
        ensure_plan_workflow_approved(folder)
    assert str(excinfo.value) == ideation.IDEATION_NO_EXECUTE_REASON


def test_legacy_approve_endpoint_refuses_with_409_not_a_500(client, tmp_path):
    """The gate held before this, but the refusal escaped as an unhandled 500."""
    from agent_lab.run.meta import patch_run_meta

    folder = _make_session(tmp_path)
    (folder / "plan.md").write_text("# Plan\n\n## Goal\n무언가\n", encoding="utf-8")
    patch_run_meta(
        folder,
        lambda run: {**run, "plan_workflow": {"enabled": True, "phase": "HUMAN_PENDING"}},
    )
    _patch(client, folder.name, command="select", option_id="opt-0-codex")

    res = client.post(f"/api/sessions/{folder.name}/plan/approve", json={})
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == ideation.IDEATION_NO_EXECUTE_REASON
    assert "APPROVED" not in (folder / "run.json").read_text(encoding="utf-8")


def test_the_approve_endpoint_still_works_for_an_execute_lane_session(client, tmp_path):
    """Guard: the 409 above must come from the idea lane, not a broken endpoint."""
    from agent_lab.plan.pending import plan_content_hash
    from agent_lab.run.meta import patch_run_meta

    plan_md = "# Plan\n\n## Goal\n무언가 한다\n"
    folder = _make_session(tmp_path, with_ideation=False)
    (folder / "plan.md").write_text(plan_md, encoding="utf-8")
    patch_run_meta(
        folder,
        lambda run: {
            **run,
            "plan_workflow": {
                "enabled": True,
                "phase": "HUMAN_PENDING",
                "plan_hash_at_approval": plan_content_hash(plan_md),
            },
        },
    )

    res = client.post(f"/api/sessions/{folder.name}/plan/approve", json={})
    assert res.status_code == 200
    assert "APPROVED" in (folder / "run.json").read_text(encoding="utf-8")


# --- agreement with the real room round ----------------------------------


def test_the_api_reflects_what_a_real_room_round_produced(client, tmp_path, monkeypatch):
    """continue_room_round() must leave the state the API then serves."""
    from agent_lab.room import continue_room_round

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    folder = _make_session(tmp_path)
    # start from an empty candidate set so the round is what fills it
    from agent_lab.run.meta import patch_run_meta

    def _clear(run):
        run["ideation"] = {**run["ideation"], "options": []}
        return run

    patch_run_meta(folder, _clear)

    continue_room_round(folder, "막연한 개념", agents=["cursor", "codex"], parallel_rounds=1)

    body = client.get(f"/api/sessions/{folder.name}/ideation").json()
    options = body["ideation"]["options"]
    assert options, "a room round on the idea lane must leave candidates behind"
    assert body["revision"] >= 1

    # and the ids the API serves are selectable
    chosen = options[0]["id"]
    res = _patch(client, folder.name, command="select", option_id=chosen)
    assert res.status_code == 200
    assert res.json()["ideation"]["selection"]["option_id"] == chosen


def test_a_room_round_does_not_start_execution(client, tmp_path, monkeypatch):
    from agent_lab.room import continue_room_round
    from agent_lab.run.meta import read_run_meta

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    folder = _make_session(tmp_path)
    continue_room_round(folder, "막연한 개념", agents=["cursor"], parallel_rounds=1)

    run = read_run_meta(folder)
    assert not run.get("executions")
    assert "mission_loop" not in run
    assert not (folder / "plan.md").exists()
