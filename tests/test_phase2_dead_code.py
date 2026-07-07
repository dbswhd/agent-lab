"""Phase 2 dead-code queue — grep evidence (CLEANUP-PHASE0-SCOPE §5).

One PR may close one or more rows when evidence shows the surface is gone.
"""

from __future__ import annotations

from ui_surface_bundles import room_chat_surface
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def test_legacy_turn_profile_segmented_picker_absent_from_ui() -> None:
    """Legacy discuss/analyze/review/free segmented picker removed (TURN-MODES §3)."""
    composer = _read("web", "src", "components", "ChatComposer.tsx")
    room = room_chat_surface()
    composer_prefs = _read("web", "src", "utils", "roomComposerPrefs.ts")
    # P2: topic-only composer — implicit supervisor; no fast/supervisor picker.
    assert "TOPIC_ONLY_COMPOSER" in composer_prefs
    assert "composer-preset-seg" not in composer
    assert "roomPreset" not in composer
    for legacy in (
        'aria-label="discuss"',
        "TurnProfileSegmented",
        "segmented-turn-profile",
        "♾️</button>",
    ):
        assert legacy not in composer
        assert legacy not in room


def test_settings_topology_six_button_ui_absent() -> None:
    """RO-P1: Settings must not expose a 6-topology button grid."""
    settings = _read("web", "src", "components", "SettingsPage.tsx")
    for token in (
        "producer_reviewer",
        "topology-picker",
        "topologySix",
        "six-topology",
    ):
        assert token not in settings


def test_orchestrator_inbox_harvest_is_opt_in_only() -> None:
    """MCP-first: harvest default off; flag remains as explicit legacy opt-in."""
    harvest = _read("src", "agent_lab", "inbox", "harvest.py")
    flags = _read("src", "agent_lab", "runtime_flags.py")
    assert 'os.getenv("AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST", "0")' in harvest
    assert "AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST" in flags


def test_synthesize_only_is_dedicated_path() -> None:
    """TurnPolicy Human override — not mode=plan / synthesize=true."""
    room = _read("app", "server", "routers", "room.py")
    client = _read("web", "src", "api", "client.ts")
    verified = _read("web", "src", "hooks", "useRoomVerifiedHandlers.ts")
    assert "_stream_synthesize_only" in room
    assert 'workflow": "room.synthesize_only"' in room or "room.synthesize_only" in room
    assert "runSynthesizeOnly" in client
    assert "runSynthesizeOnly" in verified
    # Normal agent sends no longer flip mode=plan for synthesizeOnly.
    assert 'form.append("mode", "discuss")' in client
    # P1: TurnPolicy ON ignores deprecated mode=plan / synthesize hints on casual send.
    assert "turn_policy_enabled()" in room
    assert "synthesize = False" in room
