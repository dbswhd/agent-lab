"""Wave B — room/context package layout guard (STRUCTURE-REFACTOR-WAVE §Wave B)."""

from __future__ import annotations

from pathlib import Path

import agent_lab.room.context as rc

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONTEXT_PKG = _REPO_ROOT / "src" / "agent_lab" / "room" / "context"

_WAVE_B_MODULES = frozenset(
    {
        "__init__.py",
        "_shared.py",
        "constraints.py",
        "peer_digest.py",
        "plan_excerpt.py",
        "message_trim.py",
    }
)


def test_no_monolithic_room_context_py() -> None:
    assert not (_REPO_ROOT / "src" / "agent_lab" / "room" / "context.py").exists()


def test_wave_b_submodules_present() -> None:
    names = {p.name for p in _CONTEXT_PKG.iterdir() if p.suffix == ".py"}
    assert _WAVE_B_MODULES <= names


def test_facade_reexports_key_symbols() -> None:
    for name in (
        "build_constraints_block",
        "prepare_recent_messages",
        "format_peer_block",
        "extract_open_bullets",
        "agent_tool_rules",
    ):
        assert hasattr(rc, name), f"missing facade export: {name}"
