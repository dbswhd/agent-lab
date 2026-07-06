"""Bundled UI surface reads for F9 split components (contract tests)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def room_chat_orchestrator() -> str:
    """useRoomChat facade + bootstrap + interactions + presentation (+ types)."""
    return "\n".join(
        [
            _read("web/src/hooks/useRoomChat.ts"),
            _read("web/src/hooks/useRoomChatBootstrap.ts"),
            _read("web/src/hooks/useRoomChatInteractions.ts"),
            _read("web/src/hooks/useRoomChatPresentation.ts"),
            _read("web/src/hooks/roomChatTypes.ts"),
        ]
    )


def room_chat_surface(*, include_orchestrator: bool = False) -> str:
    """Room shell after F9 split: entry + view (+ optional useRoomChat modules)."""
    parts = [
        _read("web/src/components/RoomChat.tsx"),
        _read("web/src/components/RoomChatView.tsx"),
    ]
    if include_orchestrator:
        parts.append(room_chat_orchestrator())
    return "\n".join(parts)
