"""F12 Stage 2 — orchestration layer import-cycle guards."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "src" / "agent_lab" / "core"


def test_layer_cycle_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/layer_cycle_check.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_core_has_no_agent_lab_imports() -> None:
    """core/ must remain dependency-zero (stdlib only)."""
    offenders: list[str] = []
    for path in sorted(CORE_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if (
                    node.module
                    and node.module.startswith("agent_lab.")
                    and not node.module.startswith("agent_lab.core.")
                ):
                    offenders.append(f"{path.name}: from {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("agent_lab.") and not alias.name.startswith("agent_lab.core."):
                        offenders.append(f"{path.name}: import {alias.name}")
    assert offenders == [], offenders


def test_runtime_room_module_level_cycle_absent() -> None:
    """F12 slice: runtime↔room import-time cycle cut via core.exceptions."""
    baseline = json.loads((ROOT / "tests/fixtures/layer-cycles-baseline.json").read_text())
    cycles = {tuple(row) for row in baseline["two_cycles"]}
    assert ("runtime", "room") not in cycles
    assert ("room", "runtime") not in cycles


def test_session_cross_package_two_cycles_absent() -> None:
    """F12 slice 2: session↔mission/plan/room cycles cut via core read helpers."""
    baseline = json.loads((ROOT / "tests/fixtures/layer-cycles-baseline.json").read_text())
    cycles = {tuple(row) for row in baseline["two_cycles"]}
    for pair in (
        ("mission", "session"),
        ("plan", "session"),
        ("room", "session"),
        ("context", "room"),
    ):
        assert pair not in cycles


def test_f12_stage2_no_two_cycles() -> None:
    """F12 Stage 2 closure — orchestration 2-cycles eliminated."""
    baseline = json.loads((ROOT / "tests/fixtures/layer-cycles-baseline.json").read_text())
    assert baseline["two_cycles"] == []


def test_core_exports_runtime_event_and_pre_execute_blocked() -> None:
    from agent_lab.core import PreExecuteBlocked, RuntimeEvent
    from agent_lab.core import Layer, TurnLoopPhase
    from agent_lab.core import get_mission_loop, list_objections

    assert RuntimeEvent.TURN_START.value == "turn.start"
    assert issubclass(PreExecuteBlocked, Exception)
    assert Layer.RUNTIME.value == "runtime"
    assert TurnLoopPhase.ROUTING.value == "routing"
    assert get_mission_loop(None)["phase"] == "MISSION_DEFINE"
    assert list_objections(None) == []
