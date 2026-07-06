"""N4 Autonomy Ladder v1 — UI + API contract (source checks)."""

from __future__ import annotations

from ui_surface_bundles import room_chat_orchestrator, room_chat_surface
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def test_autonomy_dial_in_session_header() -> None:
    room = room_chat_surface()
    orchestrator = room_chat_orchestrator()
    chrome = _read("web", "src", "components", "WorkspaceChrome.tsx")
    dial = _read("web", "src", "components", "AutonomyDial.tsx")
    hook = _read("web", "src", "hooks", "useAutonomySession.ts")
    layout = _read("web", "src", "styles", "layout.css")

    assert "useRoomChat" in room
    assert "useAutonomySession" in orchestrator
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
    assert "autonomy?: {" in client
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


def test_autonomy_v2_human_picker_and_patch() -> None:
    room = room_chat_surface()
    dial = _read("web", "src", "components", "AutonomyDial.tsx")
    hook = _read("web", "src", "hooks", "useAutonomySession.ts")
    client = _read("web", "src", "api", "client.ts")
    runtime_router = _read("app", "server", "routers", "runtime.py")
    layout = _read("web", "src", "styles", "layout.css")

    assert "setAutonomyLevel" in room
    assert "onLevelChange={chat.setAutonomyLevel}" in room
    assert "autonomy-dial__popover" in dial
    assert "onLevelChange" in dial
    assert "patchSessionAutonomy" in hook
    assert "setLevel" in hook
    assert "patchSessionAutonomy" in client
    assert "patch_session_autonomy" in runtime_router
    assert ".autonomy-dial__popover" in layout


def test_autonomy_inbox_linked_transitions() -> None:
    inbox_mod = _read("src", "agent_lab", "autonomy_inbox.py")
    human_inbox = _read("src", "agent_lab", "human_inbox.py")
    panel = _read("web", "src", "components", "HumanInboxPanel.tsx")
    ladder = _read("src", "agent_lab", "autonomy_ladder.py")

    assert "maybe_create_autonomy_demotion_inbox" in inbox_mod
    assert "handle_autonomy_inbox_resolve" in inbox_mod
    assert "handle_autonomy_inbox_resolve" in human_inbox
    assert 'kind") == "autonomy"' in human_inbox
    assert "maybe_create_autonomy_demotion_inbox" in ladder
    assert 'item.kind === "autonomy"' in panel
    assert "T-A0" in panel
