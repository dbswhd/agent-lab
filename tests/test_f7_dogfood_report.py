"""F7 dogfood report + context quality instrumentation."""

from __future__ import annotations

import json
from pathlib import Path

from agent_lab.context.bundle import ContextBundleMeta, _record_context_bundle_metrics


def test_record_context_bundle_metrics_stamps_f7_fields(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_REPO_MAP", "1")
    monkeypatch.setenv("AGENT_LAB_COMPACT_TOOL_OUTPUT", "1")
    run_meta: dict = {}
    meta = ContextBundleMeta(agent="cursor", parallel_round=1, review_mode=False)
    meta.budget_pct = 42.0
    meta.trim_level = "ok"
    _record_context_bundle_metrics(run_meta, meta, agent="cursor", mode="full")
    bundle = run_meta["last_context_bundle"]
    assert bundle["repo_layer"] == "repo_map"
    assert bundle["repo_map_enabled"] is True
    assert bundle["compact_tool_output"] is True
    assert run_meta["context_quality_log"]
    assert run_meta["context_quality_log"][-1]["repo_layer"] == "repo_map"


def test_record_context_bundle_metrics_off_parity(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_REPO_MAP", raising=False)
    monkeypatch.delenv("AGENT_LAB_COMPACT_TOOL_OUTPUT", raising=False)
    run_meta: dict = {}
    meta = ContextBundleMeta(agent="codex", parallel_round=1, review_mode=False)
    _record_context_bundle_metrics(run_meta, meta, agent="codex", mode="full")
    bundle = run_meta["last_context_bundle"]
    assert bundle["repo_layer"] == "repo_tree"
    assert bundle["repo_map_enabled"] is False
    assert bundle["compact_tool_output"] is False


def test_f7_report_gates(tmp_path: Path, monkeypatch) -> None:
    import importlib.util

    monkeypatch.delenv("AGENT_LAB_REPO_MAP", raising=False)
    sessions = tmp_path / "sessions"
    for i in range(10):
        folder = sessions / f"sess-{i:02d}"
        folder.mkdir(parents=True)
        (folder / "run.json").write_text(
            json.dumps(
                {
                    "last_context_bundle": {
                        "repo_layer": "repo_map",
                        "repo_map_enabled": True,
                        "compact_tool_output": True,
                        "budget_pct": 40.0,
                        "trim_level": "ok",
                    },
                    "context_quality_log": [
                        {
                            "repo_layer": "repo_map",
                            "budget_pct": 40.0,
                            "compact_tool_output": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
    path = Path(__file__).resolve().parents[1] / "scripts" / "f7_dogfood_report.py"
    spec = importlib.util.spec_from_file_location("f7_dogfood_report", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = mod.collect_sessions(sessions, days=30)
    report = mod.build_report(rows)
    assert report["sessions"] == 10
    assert report["f7_instrumented_sessions"] == 10
    assert report["repo_map_coverage_pct"] == 100.0
    assert report["ready_for_decision"] is True


def test_f7_report_surfaces_legacy_context_sessions(tmp_path: Path) -> None:
    import importlib.util

    sessions = tmp_path / "sessions"
    folder = sessions / "legacy-context"
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(
        json.dumps(
            {
                "last_turn": {
                    "context": {
                        "agents": [
                            {
                                "agent": "codex",
                                "budget_pct": 12.0,
                                "trim_level": "ok",
                            }
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    path = Path(__file__).resolve().parents[1] / "scripts" / "f7_dogfood_report.py"
    spec = importlib.util.spec_from_file_location("f7_dogfood_report", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = mod.collect_sessions(sessions, days=30)
    report = mod.build_report(rows)
    assert report["sessions"] == 1
    assert report["f7_instrumented_sessions"] == 0
    assert report["missing_f7_instrumentation_sessions"] == 1
    assert report["median_budget_pct"] == 12.0


def test_f7_report_writes_json_and_markdown_artifacts(tmp_path: Path) -> None:
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "f7_dogfood_report.py"
    spec = importlib.util.spec_from_file_location("f7_dogfood_report", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    report = mod.build_report(
        [
            {
                "session_id": "sess-1",
                "repo_layer": "repo_map",
                "repo_map_enabled": True,
                "compact_tool_output": True,
                "f7_instrumented": True,
                "budget_pct_median": 22.0,
            }
        ]
    )
    paths = mod.write_report_artifacts(report, tmp_path)
    assert Path(paths["json"]).is_file()
    assert Path(paths["markdown"]).is_file()
    assert "sess-1" in Path(paths["markdown"]).read_text(encoding="utf-8")


def test_compact_tool_output_default_off(monkeypatch) -> None:
    from agent_lab.room.context.message_trim import _compact_tool_output_enabled

    monkeypatch.delenv("AGENT_LAB_COMPACT_TOOL_OUTPUT", raising=False)
    assert _compact_tool_output_enabled() is False
    monkeypatch.setenv("AGENT_LAB_COMPACT_TOOL_OUTPUT", "1")
    assert _compact_tool_output_enabled() is True
