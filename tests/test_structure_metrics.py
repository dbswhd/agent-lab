"""Structure metrics and room import graph tooling."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_structure_metrics_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/structure_metrics.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_structure_metrics_baseline_has_zero_tracked_pycache() -> None:
    baseline = json.loads((ROOT / "tests/fixtures/structure-metrics-baseline.json").read_text())
    assert baseline["tracked_pycache_files"] == 0


def test_f9_hot_path_py_caps_in_baseline() -> None:
    """F9 ratchet: hot-path Python LOC caps are pinned in structure-metrics baseline."""
    baseline = json.loads((ROOT / "tests/fixtures/structure-metrics-baseline.json").read_text())
    by_path = {row["path"]: row["lines"] for row in baseline["hot_path_py_files"]}
    assert by_path == {
        "src/agent_lab/plan/execute.py": 88,
        "src/agent_lab/plan/workflow.py": 115,
        "src/agent_lab/room/turn_flow.py": 21,
    }


def test_room_facade_no_underscore_exports() -> None:
    """F9 Stage 3: room/__init__.py public facade must not re-export _-prefixed internals."""
    init = (ROOT / "src/agent_lab/room/__init__.py").read_text(encoding="utf-8")
    import ast

    tree = ast.parse(init)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    names = node.value.elts  # type: ignore[attr-defined]
                    unders = [
                        elt.value
                        for elt in names
                        if isinstance(elt, ast.Constant)
                        and isinstance(elt.value, str)
                        and elt.value.startswith("_")
                    ]
                    assert unders == [], f"underscore exports remain: {unders}"


def test_f9_hot_path_py_growth_fails_check(tmp_path: Path) -> None:
    """Simulated LOC growth on a hot-path file must fail --check."""
    import importlib.util
    import sys

    mod_name = "structure_metrics_f9_test"
    spec = importlib.util.spec_from_file_location(
        mod_name,
        ROOT / "scripts" / "structure_metrics.py",
    )
    assert spec and spec.loader
    sm = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = sm
    spec.loader.exec_module(sm)

    metrics = sm.collect_metrics()
    baseline = json.loads((ROOT / "tests/fixtures/structure-metrics-baseline.json").read_text())
    mutated = json.loads(json.dumps(baseline))
    for row in mutated["hot_path_py_files"]:
        if row["path"] == "src/agent_lab/plan/execute.py":
            row["lines"] = int(metrics.hot_path_py_files[0]["lines"]) - 1

    fake_baseline = tmp_path / "structure-metrics-baseline.json"
    fake_baseline.write_text(json.dumps(mutated, indent=2) + "\n", encoding="utf-8")
    sm.BASELINE_PATH = fake_baseline

    failures = sm._check_against_baseline(metrics)
    assert any("hot_path_py_files" in f and "execute.py" in f for f in failures)


def test_mypy_room_ratchet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mypy_room_ratchet.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_audit_room_legacy_imports_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_room_legacy_imports.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mypy_agent_ratchet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mypy_agent_ratchet.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mypy_mission_ratchet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mypy_mission_ratchet.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_audit_agent_legacy_imports_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_agent_legacy_imports.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mypy_quant_ratchet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mypy_quant_ratchet.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mypy_wisdom_ratchet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mypy_wisdom_ratchet.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mypy_inbox_ratchet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mypy_inbox_ratchet.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_audit_quant_legacy_imports_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_quant_legacy_imports.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_audit_wisdom_legacy_imports_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_wisdom_legacy_imports.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_audit_inbox_legacy_imports_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_inbox_legacy_imports.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mypy_context_ratchet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mypy_context_ratchet.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mypy_run_ratchet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mypy_run_ratchet.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_audit_context_legacy_imports_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_context_legacy_imports.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_audit_run_legacy_imports_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_run_legacy_imports.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mypy_workspace_ratchet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mypy_workspace_ratchet.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mypy_research_ratchet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mypy_research_ratchet.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_audit_workspace_legacy_imports_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_workspace_legacy_imports.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_audit_research_legacy_imports_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_research_legacy_imports.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_audit_vendor_legacy_imports_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_vendor_legacy_imports.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mypy_cursor_ratchet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mypy_vendor_ratchet.py", "--package", "cursor", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mypy_codex_ratchet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mypy_vendor_ratchet.py", "--package", "codex", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mypy_claude_ratchet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mypy_vendor_ratchet.py", "--package", "claude", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mypy_local_ratchet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mypy_vendor_ratchet.py", "--package", "local", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mypy_kimi_ratchet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mypy_kimi_ratchet.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mypy_session_ratchet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mypy_session_ratchet.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mypy_plan_ratchet_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mypy_plan_ratchet.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_audit_plan_legacy_imports_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_plan_legacy_imports.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_audit_mission_legacy_imports_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_mission_legacy_imports.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_audit_kimi_legacy_imports_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_kimi_legacy_imports.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_audit_session_legacy_imports_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_session_legacy_imports.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_plan_import_graph_collects_modules() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/plan_import_graph.py", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["plan_module_count"] == 30
    assert "plan.refs" in payload["modules"]
    assert "plan.execute" in payload["modules"]


def test_room_import_graph_strict_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/room_import_graph.py", "--strict"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_room_import_graph_collects_modules() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/room_import_graph.py", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["room_module_count"] == 41
    assert "room.delegate" in payload["modules"]
    hub_modules = {row["module"] for row in payload["hub_modules"]}
    assert "room.session_persist" in hub_modules
    assert "room.turn_flow" in payload["modules"]
