"""Integration module registry — keep slow suites out of make test-fast."""

from __future__ import annotations

import inspect
import subprocess
from pathlib import Path

import tests.conftest as conftest

ROOT = Path(__file__).resolve().parents[1]


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
            str(ROOT / ".venv" / "bin" / "pytest"),
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
    assert count <= 900, f"test-fast bucket grew to {count}; mark slow modules integration"


def test_integration_registry_is_frozen_set():
    src = inspect.getsource(conftest)
    assert "_INTEGRATION_MODULES = frozenset(" in src
