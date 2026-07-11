"""ABSORB P1 — Needs input status util contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_needs_input_status_util_exists() -> None:
    path = ROOT / "web" / "src" / "utils" / "needsInputStatus.ts"
    text = path.read_text(encoding="utf-8")
    assert "buildNeedsInputStatus" in text
    assert "plan_approval" in text
    assert "execute_approval" in text
    assert "inbox_question" in text


def test_needs_input_badge_wired_in_room_chat_view() -> None:
    view = (ROOT / "web" / "src" / "components" / "RoomChatView.tsx").read_text(encoding="utf-8")
    assert "NeedsInputBadge" in view
    assert "buildNeedsInputStatus" in view
    badge = (ROOT / "web" / "src" / "components" / "NeedsInputBadge.tsx").read_text(encoding="utf-8")
    assert 'data-testid="needs-input-badge"' in badge


def test_composer_steer_affordance() -> None:
    composer = (ROOT / "web" / "src" / "components" / "ChatComposer.tsx").read_text(encoding="utf-8")
    assert "steerEligible" in composer
    assert 'data-testid="composer-steer"' in composer
    assert "steerSession" in (ROOT / "web" / "src" / "api" / "client.ts").read_text(encoding="utf-8")


def test_steer_router_registered() -> None:
    main = (ROOT / "app" / "server" / "main.py").read_text(encoding="utf-8")
    assert "steer.router" in main
    assert (ROOT / "app" / "server" / "routers" / "steer.py").is_file()
    assert (ROOT / "src" / "agent_lab" / "steer.py").is_file()
