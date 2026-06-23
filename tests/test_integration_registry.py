"""Integration module registry — keep slow suites out of make test-fast."""

from __future__ import annotations

import inspect
import shutil
import subprocess
from pathlib import Path

import tests.conftest as conftest

ROOT = Path(__file__).resolve().parents[1]


def _resolve_pytest() -> str:
    venv = ROOT / ".venv" / "bin" / "pytest"
    if venv.is_file():
        return str(venv)
    on_path = shutil.which("pytest")
    if on_path:
        return on_path
    raise FileNotFoundError("pytest not found (.venv/bin/pytest or PATH)")


def test_integration_modules_include_profiled_slow_suites():
    """Modules profiled >10s in test-fast (2026-06-14) must stay integration-tagged."""
    required = {
        "test_discuss_objections",
        "test_plan_execute_worktree",
        "test_plan_execute_revise_api",
        "test_plan_execute_agent_repair",
        "test_live_execute_spike",
        "test_dev_preview_api",
        "test_dev_preview_probe",
        "test_human_inbox",
        "test_context_bundle",
        "test_plan_execute",
        "test_recombination",
        "test_topic_router",
    }
    registered = set(conftest._INTEGRATION_MODULES)
    missing = sorted(required - registered)
    assert not missing, f"Add to _INTEGRATION_MODULES: {missing}"


def test_fast_bucket_collection_budget():
    """test-fast should stay a PR-sized subset (integration carries the rest)."""
    proc = subprocess.run(
        [
            _resolve_pytest(),
            "tests/",
            "--collect-only",
            "-q",
            "-m",
            "not live and not integration",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    line = proc.stdout.strip().splitlines()[-1]
    count = int(line.split("/")[0])
    # 2026-06-17: raised 1100 -> 1150 for the divergence / token-efficiency /
    # run-lock-recovery fast unit suites (genuinely fast, belong in the fast lane).
    # 2026-06-18: raised 1150 -> 1200 for the AGENT_LAB_PIPELINE transplant fast unit
    # suites (clarity scorer, mode router, goal ledger, CLARIFY scaffold).
    # 2026-06-18: raised 1200 -> 1300 for the AGENT_LAB_DYNAMIC_ROOM fast unit suites
    # (provider registry, account chain, agent roster, consensus floor, slash commands).
    # 2026-06-19: raised 1300 -> 1320 for kimi_work P3-P4 fast suites (supervisor, session, smoke).
    # 2026-06-19: raised 1320 -> 1340 for AGENT_LAB_COMMS_COMPACT token-compaction suites (pin cap + peer digest).
    # 2026-06-19: raised 1340 -> 1360 for §1 pipeline handles (/pipeline,/clarify,/plan) + CLARIFY transition rows.
    # 2026-06-19: raised 1360 -> 1380 for model-switch safety probe (substitute recognition + 2-stage live capability).
    # 2026-06-20: raised 1380 -> 1400 for §5 Phase 0 code-memory MCP pilot (server + contract + mount + off-parity + cache).
    # 2026-06-21: raised 1400 -> 1430 for CLARIFY unification (clarifier_engine adapter AC1-AC15 suite).
    # 2026-06-22: raised 1430 -> 1560 for stage-aware routing + anti-drift (phase->route resolver, RoutingDecisionLog telemetry, anti-drift A/B + fresh-eyes seat, and adversarial red-team suites).
    assert count <= 1560, f"test-fast bucket grew to {count}; mark slow modules integration"


def test_integration_registry_is_frozen_set():
    src = inspect.getsource(conftest)
    assert "_INTEGRATION_MODULES = frozenset(" in src
