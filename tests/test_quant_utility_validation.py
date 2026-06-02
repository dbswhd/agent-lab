"""Quant workspace utility validation (mock-safe)."""

from __future__ import annotations

from agent_lab.quant_utility_validation import build_report, detect_pipeline_root


def test_quant_utility_validation_mock(tmp_path, monkeypatch):
    pipeline = tmp_path / "pipeline"
    pipeline.mkdir()
    (pipeline / "research/kr/sector_rotation").mkdir(parents=True)
    (pipeline / "research/kr/sector_rotation/sector_rotation.py").write_text("# stub\n")
    (pipeline / "research/kr/results/sector_rotation").mkdir(parents=True)
    app_pages = pipeline / "apps/quant-control-app/src/pages"
    app_pages.mkdir(parents=True)
    (app_pages / "overlays-hub.tsx").write_text("// kr_kospi_v1\n")
    tauri = pipeline / "apps/quant-control-app/src-tauri/src"
    tauri.mkdir(parents=True)
    (tauri / "lib.rs").write_text("// overlay\n")

    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")

    report = build_report(mock=True)
    assert report.pipeline_root == str(pipeline.resolve())
    assert report.passed >= 10
    assert not report.failed, [f"{c.name}: {c.detail}" for c in report.failed]


def test_detect_pipeline_root_prefers_env(tmp_path, monkeypatch):
    custom = tmp_path / "custom-pipe"
    custom.mkdir()
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(custom))
    assert detect_pipeline_root() == custom.resolve()
