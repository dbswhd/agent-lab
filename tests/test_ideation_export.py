"""RI-11 — exporting the concept + plan, and what it must not do."""

from __future__ import annotations

import subprocess

import pytest

from agent_lab import ideation
from agent_lab.ideation_export import EXPORT_SCHEMA, export_filename, export_markdown
from agent_lab.run.state import RunState

pytest.importorskip("fastapi")

PLAN_MD = """# Plan

## 지금 실행
1.
   - 무엇을: 알림 스케줄러를 만든다
   - 어디서: `app/notify.py`
   - 검증: 밤 10시에 알림 1건이 도착한다
"""

OPTIONS = [
    {
        "id": "opt-0-cursor",
        "title": "하루 한 줄 회고",
        "principle": "매일 밤 알림 하나",
        "usage": "자기 전 한 줄",
        "difference": "길게 못 쓴다",
        "tradeoff": "깊은 기록 불가",
        "first_experiment": "종이로 2주",
    },
    {"id": "opt-0-claude", "title": "음성 메모", "principle": "말로 남긴다"},
]


@pytest.fixture()
def no_subprocess(monkeypatch):
    """Export is a read — nothing here may shell out."""
    calls: list[object] = []

    def _boom(*args, **kwargs):
        calls.append(args)
        raise AssertionError(f"unexpected subprocess call: {args!r}")

    for name in ("run", "check_output", "check_call", "Popen", "call"):
        monkeypatch.setattr(subprocess, name, _boom)
    return calls


def _run(*, select: bool = True, **brief) -> RunState:
    run = RunState.from_memory({"topic": "하루를 정리하는 뭔가"})
    ideation.start_ideation(run, ideation.new_ideation(original_concept="하루를 정리하는 뭔가", **brief))
    ideation.mutate_ideation(run, ideation.set_options(OPTIONS))
    ideation.mutate_ideation(run, ideation.reject_option("opt-0-claude", reason="소리내기 싫다"))
    if select:
        ideation.mutate_ideation(run, ideation.select_option("opt-0-cursor", reason="가장 작다"))
    return run


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import agent_lab.session as session_mod
    import app.server.deps as deps_mod

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)

    from app.server.main import app

    return TestClient(app)


def _session(tmp_path, run: RunState | None = None, *, plan: str = PLAN_MD, name: str = "sess"):
    from agent_lab.run.meta import write_run_meta

    folder = tmp_path / name
    folder.mkdir(exist_ok=True)
    (folder / "topic.txt").write_text("하루를 정리하는 뭔가\n", encoding="utf-8")
    if plan:
        (folder / "plan.md").write_text(plan, encoding="utf-8")
    write_run_meta(folder, dict(run if run is not None else RunState.from_memory({"topic": "t"})))
    return folder


# --- document content (§4.4) --------------------------------------------


def test_document_carries_the_direction_and_why_it_was_chosen():
    md = export_markdown(_run(), topic="하루를 정리하는 뭔가", plan_md=PLAN_MD)

    assert md.startswith("# 하루를 정리하는 뭔가")
    assert "## 고른 구상" in md
    assert "하루 한 줄 회고" in md
    assert "가장 작다" in md
    assert "매일 밤 알림 하나" in md


def test_wrapper_headings_do_not_collide_with_the_plan_body():
    """The plan body brings its own §4.4 headings; a duplicate is confusing."""
    plan = "## 만들려는 것\n본문\n\n## 첫 작업 지시문\n> 시작하세요\n"
    md = export_markdown(_run(), plan_md=plan)

    for heading in ("## 만들려는 것", "## 첫 작업 지시문"):
        assert md.count(heading) == 1, f"{heading} appears more than once"
    assert "## 고른 구상" in md


def test_document_carries_the_plan_with_its_verification():
    md = export_markdown(_run(), plan_md=PLAN_MD)
    assert "## 구현 계획" in md
    assert "알림 스케줄러를 만든다" in md
    assert "검증: 밤 10시에 알림 1건이 도착한다" in md


def test_document_says_so_when_no_plan_exists_yet():
    md = export_markdown(_run(), plan_md="")
    assert "아직 계획이 작성되지 않았습니다" in md
    assert "계획 미작성" in md
    assert "계획 상태: missing" in md


def test_document_keeps_rejections_and_their_reasons():
    md = export_markdown(_run(), plan_md=PLAN_MD)
    assert "## 이미 기각한 방향" in md
    assert "음성 메모" in md
    assert "소리내기 싫다" in md
    assert "새 근거 없이 다시 제안하지 마세요" in md


def test_document_keeps_assumptions_and_open_questions():
    """The part a polished plan most often smooths over."""
    run = _run(assumptions=["사용자는 알림을 켠다"], open_questions=["혼자 쓰나?"])
    md = export_markdown(run, plan_md=PLAN_MD)

    assert "## 아직 확인되지 않은 것" in md
    assert "가정 (사실 아님)" in md
    assert "사용자는 알림을 켠다" in md
    assert "혼자 쓰나?" in md


def test_document_carries_a_changed_condition_including_what_was_dropped():
    run = _run(constraints=["웹에서 쓴다"])
    ideation.mutate_ideation(run, ideation.change_condition(constraints=["iPhone에서만"], reason="웹은 안 열더라"))
    md = export_markdown(run, plan_md=PLAN_MD)

    assert "## 바뀐 조건" in md
    assert "constraints 해제: 웹에서 쓴다" in md
    assert "이전 논의보다 아래가 우선합니다" in md


def test_document_states_the_revision_it_reflects():
    run = _run()
    revision = ideation.read_ideation(run)["revision"]
    md = export_markdown(run, plan_md=PLAN_MD)
    assert f"구상 revision: **{revision}**" in md
    assert EXPORT_SCHEMA in md


def test_document_grants_no_execution_authority():
    md = export_markdown(_run(), plan_md=PLAN_MD)
    assert "실행하지 않았고" in md
    assert "승인 권한을 포함하지 않습니다" in md


# --- warnings ------------------------------------------------------------


def test_a_stale_plan_is_flagged_with_both_revisions():
    run = _run()
    ideation.stamp_plan_source(run, PLAN_MD)
    at_stamp = ideation.read_ideation(run)["revision"]
    assert "오래됐습니다" not in export_markdown(run, plan_md=PLAN_MD)

    ideation.mutate_ideation(run, ideation.change_condition(constraints=["iPhone에서만"]))
    md = export_markdown(run, plan_md=PLAN_MD)

    assert "계획이 최신 구상보다 오래됐습니다" in md
    assert f"revision {at_stamp} 기준" in md


def test_an_open_block_is_named_not_summarized_away():
    md = export_markdown(
        _run(),
        plan_md=PLAN_MD,
        objections=[{"agent": "claude", "text": "알림 권한 없이는 동작하지 않는다", "refs": ["chat.jsonl#L42"]}],
    )
    assert "미결 BLOCK이 있습니다" in md
    assert "claude: 알림 권한 없이는 동작하지 않는다" in md
    assert "chat.jsonl#L42" in md
    assert "확정본으로 다루지 마세요" in md


def test_no_selection_exports_a_conditional_document():
    md = export_markdown(_run(select=False), plan_md=PLAN_MD)
    assert "조건부 계획" in md
    assert "확정된 방향이 아니라" in md


def test_a_selected_document_is_not_marked_conditional():
    assert "조건부 계획" not in export_markdown(_run(), plan_md=PLAN_MD)


def test_combined_selection_is_preserved_as_review_required():
    run = _run(select=False)
    ideation.mutate_ideation(run, ideation.select_option("opt-0-cursor"))
    ideation.mutate_ideation(run, ideation.combine_options(["opt-0-cursor", "opt-0-claude"], new_id="opt-combined"))
    md = export_markdown(run, plan_md=PLAN_MD)
    assert "검토 필요" in md
    assert "조합 후보: opt-0-cursor + opt-0-claude" in md


def test_export_refuses_a_session_with_no_ideation_state():
    with pytest.raises(ideation.IdeationError):
        export_markdown(RunState.from_memory({"topic": "기존 세션"}), plan_md=PLAN_MD)


def test_filename_is_revision_stamped_and_path_safe():
    assert export_filename("sess-1", 4) == "sess-1-rev4.md"
    assert "/" not in export_filename("../../etc/passwd", 1)
    assert export_filename("", 0) == "ideation-rev0.md"


# --- endpoint ------------------------------------------------------------


def test_endpoint_returns_markdown_and_the_revision(client, tmp_path, no_subprocess):
    folder = _session(tmp_path, _run())
    res = client.get(f"/api/sessions/{folder.name}/ideation/export")

    assert res.status_code == 200
    body = res.json()
    assert body["schema"] == EXPORT_SCHEMA
    assert body["revision"] == ideation.read_ideation(_run())["revision"]
    assert body["filename"].endswith(".md")
    assert "## 구현 계획" in body["markdown"]
    assert "알림 스케줄러를 만든다" in body["markdown"]
    assert no_subprocess == []


def test_endpoint_reports_stale_and_open_blocks(client, tmp_path):
    from agent_lab.run.meta import patch_run_meta

    run = _run()
    ideation.stamp_plan_source(run, PLAN_MD)
    ideation.mutate_ideation(run, ideation.change_condition(constraints=["iPhone에서만"]))
    folder = _session(tmp_path, run)
    patch_run_meta(
        folder,
        lambda meta: {
            **meta,
            "objections": [{"id": "o1", "status": "open", "agent": "claude", "text": "권한 문제"}],
        },
    )

    body = client.get(f"/api/sessions/{folder.name}/ideation/export").json()
    assert body["plan_stale"] is True
    assert body["open_blocks"] == 1
    assert "미결 BLOCK" in body["markdown"]
    assert "오래됐습니다" in body["markdown"]


def test_endpoint_is_404_for_an_existing_session(client, tmp_path):
    folder = _session(tmp_path, name="legacy")
    assert client.get(f"/api/sessions/{folder.name}/ideation/export").status_code == 404


# --- what export must not do --------------------------------------------


def test_export_writes_nothing(client, tmp_path, no_subprocess):
    folder = _session(tmp_path, _run())
    before = {p.name: p.read_bytes() for p in folder.iterdir()}

    for _ in range(3):
        assert client.get(f"/api/sessions/{folder.name}/ideation/export").status_code == 200

    after = {p.name: p.read_bytes() for p in folder.iterdir()}
    assert after == before


def test_export_never_overwrites_a_legacy_sessions_plan(client, tmp_path, no_subprocess):
    """A legacy execute session's plan.md must survive an idea-lane export."""
    legacy_plan = "# 기존 실행 계획\n\n절대 덮어쓰면 안 된다\n"
    folder = _session(tmp_path, _run(), plan=legacy_plan)

    client.get(f"/api/sessions/{folder.name}/ideation/export")

    assert (folder / "plan.md").read_text(encoding="utf-8") == legacy_plan


def test_export_changes_no_approval_state(client, tmp_path, no_subprocess):
    from agent_lab.plan.workflow import PlanWorkflowNotApproved, ensure_plan_workflow_approved
    from agent_lab.run.meta import read_run_meta

    folder = _session(tmp_path, _run())
    client.get(f"/api/sessions/{folder.name}/ideation/export")

    run = read_run_meta(folder)
    assert "plan_workflow" not in run
    assert "mission_loop" not in run
    assert "goal_loop" not in run
    assert not run.get("executions")
    with pytest.raises(PlanWorkflowNotApproved):
        ensure_plan_workflow_approved(folder)


def test_export_does_not_bump_the_ideation_revision(client, tmp_path, no_subprocess):
    folder = _session(tmp_path, _run())
    before = client.get(f"/api/sessions/{folder.name}/ideation").json()["revision"]

    client.get(f"/api/sessions/{folder.name}/ideation/export")

    assert client.get(f"/api/sessions/{folder.name}/ideation").json()["revision"] == before
