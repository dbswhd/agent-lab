"""Coordination-topology shadow report — reads real turns[].category.coordination_topology."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "coordination_topology_report.py"
    spec = importlib.util.spec_from_file_location("coordination_topology_report", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_turn(folder: Path, *, category: str, task_type: str, topology: str, reason: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text(
        json.dumps(
            {
                "turns": [
                    {
                        "category": {
                            "value": category,
                            "task_type": task_type,
                            "coordination_topology": topology,
                            "coordination_topology_reason": reason,
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_collect_turns_ignores_sessions_without_shadow_field(tmp_path: Path) -> None:
    mod = _load_module()
    sessions = tmp_path / "sessions"
    folder = sessions / "legacy"
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(
        json.dumps({"turns": [{"category": {"value": "standard"}}]}),
        encoding="utf-8",
    )
    rows = mod.collect_turns(sessions, days=30)
    assert rows == []


def test_report_gates_need_diversity_not_just_volume(tmp_path: Path) -> None:
    mod = _load_module()
    sessions = tmp_path / "sessions"
    for i in range(25):
        _write_turn(
            sessions / f"sess-{i:02d}",
            category="standard",
            task_type="code",
            topology="single",
            reason="single lead is sufficient",
        )
    rows = mod.collect_turns(sessions, days=30)
    report = mod.build_report(rows)
    assert report["turns"] == 25
    assert report["gates"]["min_turns_20"] is True
    assert report["gates"]["at_least_2_topology_kinds"] is False
    assert report["gates"]["not_degenerate_single_only"] is False
    assert report["ready_for_manual_review"] is False


def test_report_ready_when_gates_all_pass(tmp_path: Path) -> None:
    mod = _load_module()
    sessions = tmp_path / "sessions"
    fixtures = [
        ("quick", "general", "single", "single lead is sufficient"),
        ("standard", "review", "manager_specialists", "independent domains can be parallelized"),
        ("critical", "review", "actor_critic", "evaluation rubric is clearer than generation"),
    ]
    i = 0
    for category, task_type, topology, reason in fixtures:
        for _ in range(7):
            _write_turn(
                sessions / f"sess-{i:03d}", category=category, task_type=task_type, topology=topology, reason=reason
            )
            i += 1
    rows = mod.collect_turns(sessions, days=30)
    report = mod.build_report(rows)
    assert report["turns"] == 21
    assert set(report["kind_counts"]) == {"single", "manager_specialists", "actor_critic"}
    assert all(report["gates"].values())
    assert report["ready_for_manual_review"] is True


def test_render_report_is_human_readable(tmp_path: Path) -> None:
    mod = _load_module()
    sessions = tmp_path / "sessions"
    _write_turn(
        sessions / "sess-0",
        category="quick",
        task_type="general",
        topology="single",
        reason="single lead is sufficient",
    )
    rows = mod.collect_turns(sessions, days=30)
    report = mod.build_report(rows)
    text = mod.render_report(report)
    assert "Coordination-topology shadow report" in text
    assert "single: 1" in text
