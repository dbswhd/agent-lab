from __future__ import annotations

from pathlib import Path

from agent_lab.harness_hygiene import build_harness_hygiene_report


def test_harness_hygiene_reports_broken_authoritative_links(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("[missing](./nope.md)\n", encoding="utf-8")
    report = build_harness_hygiene_report(tmp_path)
    assert report["ok"] is False
    docs = report["docs"]
    assert isinstance(docs, dict)
    assert "AGENTS.md -> ./nope.md" in docs["broken_links"]


def test_harness_hygiene_current_project_is_clean() -> None:
    report = build_harness_hygiene_report()
    assert report["ok"] is True
    assert report["trace"] == {"trace_schema_version": 2}


def test_harness_hygiene_health_surface() -> None:
    from app.server.routers.health import health_harness

    assert health_harness()["ok"] is True
