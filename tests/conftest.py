"""Pytest path: repo root so `app.server` imports work in CI and local venv."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_TESTS = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

for _qat_src in (
    Path.home() / "Projects" / "quant-agentic-trading" / "src",
    Path.home() / "Documents" / "New project" / "src",
):
    if _qat_src.is_dir() and str(_qat_src) not in sys.path:
        sys.path.insert(0, str(_qat_src.resolve()))
        break


@pytest.fixture(autouse=True)
def _mock_goal_oracle_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep goal Oracle mock-first even when .env sets AGENT_LAB_GOAL_ORACLE_LIVE=1."""
    monkeypatch.delenv("AGENT_LAB_GOAL_ORACLE_LIVE", raising=False)


@pytest.fixture(autouse=True)
def _skip_claude_headless_probe_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Most unit tests mock Claude subprocess; skip slow real OAuth probe."""
    monkeypatch.setenv("AGENT_LAB_CLAUDE_SKIP_HEADLESS_PROBE", "1")


@pytest.fixture(autouse=True)
def _isolate_room_model_env() -> object:
    """Clear room-composition env vars at setup and restore original after test.

    Tests that exercise `/model` or room_models_config write
    ``AGENT_LAB_ROOM_MODELS`` / ``AGENT_LAB_ROOM_SUBSTITUTION`` directly to
    ``os.environ`` (production behavior). This fixture gives each test a clean
    baseline so roster assertions don't inherit state from earlier tests.
    """
    import os

    keys = ("AGENT_LAB_ROOM_MODELS", "AGENT_LAB_ROOM_SUBSTITUTION")
    saved = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture(autouse=True)
def _reset_run_control_cancel() -> None:
    """Prevent cancel flag / child registry leaking across tests."""
    from agent_lab.run_control import clear_cancel, terminate_active_children

    clear_cancel()
    terminate_active_children()
    yield
    clear_cancel()
    terminate_active_children()


@pytest.fixture(autouse=True)
def _legacy_orchestrator_harvest_for_harvest_tests(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Harvest unit tests target legacy orchestrator path (flag default is off)."""
    module = request.module.__name__.rsplit(".", 1)[-1]
    if module in {
        "test_inbox_harvest",
        "test_inbox_build",
        "test_inbox_facilitator",
        "test_inbox_pause",
        "test_session_clarifier",
    }:
        monkeypatch.setenv("AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST", "1")


_INTEGRATION_MODULES = frozenset(
    {
        # Subprocess / WS / multi-step API
        "test_terminal_ws",
        "test_mission_loop",
        "test_mission_loop_e2e",
        "test_smoke_room_e2e",
        "test_inbox_execute_e2e",
        "test_quant_utility_validation",
        "test_measure_communicate_baseline",
        "test_mb_smoke_fixtures",
        "test_run_dogfood_suite",
        "test_session_score_ci",
        "test_background_tasks_api",
        "test_trading_mission_native_ingest",
        # Room mock E2E (consensus / goal auto-continue; 30–140s/test)
        "test_discuss_objections",
        "test_human_inbox",
        "test_durable_completed_steps",
        "test_analysis_turn",
        "test_recombination",
        "test_topic_router",
        "test_room_partial_turn",
        "test_room_dispatch",
        # Plan execute git worktrees / subprocess API (~30–100s/module)
        "test_plan_execute_worktree",
        "test_plan_execute",
        "test_plan_execute_revise_api",
        "test_plan_execute_reverify_api",
        "test_plan_execute_agent_repair",
        "test_live_execute_spike",
        # Heavy FastAPI boot + port probes (~5–8s/test)
        "test_dev_preview_api",
        "test_dev_preview_probe",
        # Multi-agent context bundling
        "test_context_bundle",
        "test_agent_capabilities",
        "test_room_agent_capabilities",
        "test_commands_api",
        "test_model_policy",
        "test_room_mode_contract_api",
        "test_smoke_room_governance",
        # Stabilization suites (policy/schema/stream helpers; keep PR fast bucket lean)
        "test_run_schema",
        "test_verify_repair_policy",
        "test_room_sse_stream",
        "test_claude_cli_stream",
        "test_claude_headless_auth",
    }
)

_BRIDGE_MODULES = frozenset(
    {
        "test_cursor_bridge",
        "test_health_preflight",
    }
)


def pytest_runtest_setup(item: pytest.Item) -> None:
    if item.get_closest_marker("quant"):
        from agent_lab.extensions.quant_trading import agentic_trading_available

        if not agentic_trading_available():
            pytest.skip("quant-agentic-trading extension not available")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        module = item.module.__name__.rsplit(".", 1)[-1]
        if module in _INTEGRATION_MODULES:
            item.add_marker(pytest.mark.integration)
        if module in _BRIDGE_MODULES:
            item.add_marker(pytest.mark.bridge)
        if item.get_closest_marker("quant"):
            item.add_marker(pytest.mark.integration)
