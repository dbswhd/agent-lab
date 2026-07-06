"""Extension plan path helpers."""

from __future__ import annotations

from pathlib import Path

from agent_lab.plan.paths import (
    active_plan_relpath,
    begin_session_plan_cycle,
    extract_plan_path_directive,
    is_trading_mission_run,
    read_session_plan_md,
    read_trading_plan_md,
    resolve_new_plan_relpath,
    session_plans_dir,
    trading_mission_plan_path,
    write_session_plan_md,
    write_trading_plan_md,
)
from agent_lab.plan.workflow import init_plan_workflow_on_plan_send
from agent_lab.run.meta import read_run_meta, write_run_meta


def test_trading_plan_separate_from_core_plan(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "plan.md").write_text("# core\n\n## 지금 실행\n", encoding="utf-8")
    write_trading_plan_md(folder, "# trading\n\ningest_ready: false\n")
    assert trading_mission_plan_path(folder).is_file()
    assert "ingest_ready" in read_trading_plan_md(folder)
    assert "ingest_ready" not in (folder / "plan.md").read_text(encoding="utf-8")


def test_is_trading_mission_run() -> None:
    assert is_trading_mission_run({"session_template": "trading-mission"})
    assert not is_trading_mission_run({"session_template": "general"})


def test_plan_path_directive_and_slug(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    run: dict = {}
    md = "<!-- plan-path: artifacts/plans/context-refactor.md -->\n# Context refactor\n\nBody\n"
    rel, body = extract_plan_path_directive(md)
    assert rel == "artifacts/plans/context-refactor.md"
    assert body.startswith("# Context refactor")
    path, written = write_session_plan_md(folder, md, run)
    assert written == "artifacts/plans/context-refactor.md"
    assert path.is_file()
    assert active_plan_relpath(run) == "artifacts/plans/context-refactor.md"
    assert read_session_plan_md(folder, run) == body.rstrip() + "\n"


def test_plan_cycle_archives_and_clears_active_path(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    run: dict = {"active_plan_relpath": "artifacts/plans/feature-a.md"}
    target = folder / "artifacts/plans/feature-a.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Feature A\n\nDone\n", encoding="utf-8")
    (folder / "plan.md").write_text("# mirror\n", encoding="utf-8")
    archived = begin_session_plan_cycle(folder, run)
    assert archived == "artifacts/plans/feature-a.md"
    assert "active_plan_relpath" not in run
    assert len(run["plan_cycles"]) == 1


def test_init_plan_workflow_starts_new_cycle_after_approved(tmp_path: Path) -> None:
    folder = tmp_path / "sess"
    folder.mkdir()
    run_meta = {
        "plan_workflow": {
            "enabled": True,
            "phase": "APPROVED",
            "plan_hash_at_approval": "abc",
        },
        "active_plan_relpath": "artifacts/plans/approved-plan.md",
    }
    write_run_meta(folder, run_meta)
    plan_file = folder / "artifacts/plans/approved-plan.md"
    plan_file.parent.mkdir(parents=True)
    plan_file.write_text("# Approved plan\n\n## 지금 실행\n", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    run = read_run_meta(folder)
    assert run["plan_workflow"]["phase"] == "CLARIFY"
    assert "plan_hash_at_approval" not in run["plan_workflow"]
    assert "active_plan_relpath" not in run
    assert session_plans_dir(folder).joinpath("approved-plan.md").is_file()


def test_resolve_new_plan_relpath_from_h1() -> None:
    rel = resolve_new_plan_relpath("# Login flow redesign\n\n", {})
    assert rel.endswith("-login-flow-redesign.md")
