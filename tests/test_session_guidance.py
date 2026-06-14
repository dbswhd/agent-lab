"""Session guidance: freeze, workspace binding, artifacts."""

from __future__ import annotations

import json

from agent_lab.session_guidance import (
    apply_discuss_workspace,
    build_session_guidance_block,
    detect_layout_freeze,
    infer_session_phase,
    summarize_break_report,
    sync_session_meta,
    verify_execution_artifacts,
)
from agent_lab.workspace_roots import discuss_primary_workspace


class _Msg:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content


def test_detect_layout_freeze_korean_phrase():
    assert detect_layout_freeze([_Msg("user", "지금이 딱 좋아")])
    assert detect_layout_freeze([], topic="페이지 새로 시작 더 하지 말고 freeze")


def test_sync_session_meta_clears_human_gate_and_sets_phase(tmp_path, monkeypatch):
    lecture = tmp_path / "book"
    lecture.mkdir()
    (lecture / "build.mjs").write_text("//\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_ROOT", str(tmp_path / "lab"))
    (tmp_path / "lab").mkdir()
    monkeypatch.setenv("LECTURE_SCRIPT_ROOT", str(lecture))

    run_meta: dict = {
        "human_gate_pending": True,
        "human_gate_prompt": "27p OK",
        "last_human_gate": {"status": "ng", "page_count": 27},
    }
    sync_session_meta(
        run_meta,
        topic="교재 build.mjs break-report",
        messages=[_Msg("user", "딱 좋아 freeze")],
        plan_md="- `build.mjs`",
    )
    assert run_meta["layout_frozen"] is True
    assert run_meta["session_phase"] == "content"
    assert run_meta["workspace_binding"]["path"] == str(lecture.resolve())
    assert "human_gate_pending" not in run_meta
    assert "human_gate_prompt" not in run_meta
    assert "last_human_gate" not in run_meta


def test_infer_session_phase_defaults_to_content_for_general_topic():
    assert (
        infer_session_phase(
            layout_frozen=False,
            topic="Quant control 앱 개발현황 파악해",
            plan_md="",
            messages=[],
        )
        == "content"
    )


def test_build_session_guidance_includes_frozen_block():
    block = build_session_guidance_block(
        {"layout_frozen": True, "session_phase": "content"}
    )
    assert "LAYOUT_FROZEN" in block
    assert "SINGLE_EXECUTOR" in block
    assert "27p OK" not in block
    assert "golden/" in block


def test_discuss_primary_workspace_uses_binding(tmp_path, monkeypatch):
    lecture = tmp_path / "book"
    lecture.mkdir()
    monkeypatch.setenv("AGENT_LAB_ROOT", str(tmp_path / "lab"))
    (tmp_path / "lab").mkdir()
    monkeypatch.setenv("LECTURE_SCRIPT_ROOT", str(lecture))
    perms = apply_discuss_workspace({}, {"path": str(lecture), "label": "lecture-script"})
    assert discuss_primary_workspace(perms) == lecture.resolve()


def test_summarize_break_report(tmp_path):
    path = tmp_path / "break-report.json"
    path.write_text(
        json.dumps(
            {
                "generatedAt": "2026-05-31T04:49:00Z",
                "appliedBreaks": ["a", "b"],
                "baseline": {"pdfPageCount": 26, "version": "v1"},
            }
        ),
        encoding="utf-8",
    )
    summary = summarize_break_report(path)
    assert summary is not None
    assert summary["appliedBreaksCount"] == 2
    assert summary["baselinePdfPageCount"] == 26


def test_verify_execution_artifacts_break_report_only(tmp_path):
    report = tmp_path / "break-report.json"
    report.write_text(
        json.dumps({"appliedBreaks": [], "baseline": {"pdfPageCount": 26}}),
        encoding="utf-8",
    )
    result = verify_execution_artifacts(tmp_path, [])
    assert result["break_report"] is not None
    assert result["ok"] is True
