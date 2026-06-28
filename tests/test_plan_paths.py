"""Extension plan path helpers."""

from __future__ import annotations

from pathlib import Path

from agent_lab.plan.paths import (
    is_trading_mission_run,
    read_trading_plan_md,
    trading_mission_plan_path,
    write_trading_plan_md,
)


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
