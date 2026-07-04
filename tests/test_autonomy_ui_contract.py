"""N4 Autonomy Ladder v1 — UI + API contract (source checks)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def test_autonomy_dial_in_session_header() -> None:
    room = _read("web", "src", "components", "RoomChat.tsx")
    chrome = _read("web", "src", "components", "WorkspaceChrome.tsx")
    dial = _read("web", "src", "components", "AutonomyDial.tsx")
    hook = _read("web", "src", "hooks", "useAutonomySession.ts")
    layout = _read("web", "src", "styles", "layout.css")

    assert "useAutonomySession" in room
    assert "AutonomyDial" in room
    assert "headerExtra" in chrome
    assert "workspace-chrome__pill--autonomy" in dial
    assert "autonomy-dial__level" in dial
    assert "fetchSessionRuntime" in hook
    assert "buildAutonomySessionView" in hook
    assert ".workspace-chrome__pill--autonomy" in layout


def test_autonomy_api_client_and_runtime_type() -> None:
    client = _read("web", "src", "api", "client.ts")
    runtime_router = _read("app", "server", "routers", "runtime.py")
    ladder = _read("web", "src", "utils", "autonomyLadder.ts")

    assert "fetchSessionAutonomy" in client
    assert 'autonomy?: {' in client
    assert "display_level" in client
    assert "/autonomy" in runtime_router
    assert "get_session_autonomy" in runtime_router
    assert "autonomyLevelLabel" in ladder
    assert "L0" in ladder and "L3" in ladder


def test_autonomy_ladder_ssot_module() -> None:
    ssot = _read("src", "agent_lab", "autonomy_ladder.py")
    assert "infer_effective_autonomy_level" in ssot
    assert "observe_autonomy_level_change" in ssot
    assert "record_autonomy_transition" in ssot
    assert "public_autonomy_payload" in ssot


def test_transition_audit_wired_in_trust_budget() -> None:
    tb = _read("src", "agent_lab", "trust_budget.py")
    assert "observe_autonomy_level_change" in tb
    assert "trust_budget_updated" in tb
    assert "trust_budget_consumed" in tb
