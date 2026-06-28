"""Persist agent-lab session_folder ↔ Kimi Work conversationKey mapping."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_STATE_NAME = "kimi_work.json"


def state_path(session_folder: str | Path) -> Path:
    return Path(session_folder).expanduser().resolve() / _STATE_NAME


def read_state(session_folder: str | Path) -> dict[str, Any]:
    path = state_path(session_folder)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_state(session_folder: str | Path, payload: dict[str, Any]) -> None:
    path = state_path(session_folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_conversation_key(session_folder: str | Path) -> str | None:
    key = read_state(session_folder).get("conversationKey")
    return str(key).strip() if key else None


def is_live_conversation_key(conversation_key: str | None) -> bool:
    """True for daimon-issued keys (``main:conversation:<uuid>``)."""
    key = str(conversation_key or "").strip()
    return key.startswith("main:conversation:")


def is_usable_conversation_key(conversation_key: str | None) -> bool:
    """Persisted key is valid for the current runtime (live daimon vs mock)."""
    key = str(conversation_key or "").strip()
    if not key:
        return False
    if is_live_conversation_key(key):
        return True
    if key.startswith("mock-conv-"):
        import os

        return os.getenv("AGENT_LAB_MOCK_AGENTS", "").strip().lower() in {"1", "true", "yes", "on"}
    return bool(key)


def clear_conversation_key(session_folder: str | Path) -> None:
    state = read_state(session_folder)
    if "conversationKey" not in state:
        return
    state = dict(state)
    state.pop("conversationKey", None)
    write_state(session_folder, state)


def get_workspace_path(session_folder: str | Path) -> Path | None:
    raw = read_state(session_folder).get("workspacePath")
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return Path(text).expanduser().resolve()


def _merge_state(session_folder: str | Path, **updates: Any) -> dict[str, Any]:
    state = read_state(session_folder)
    state.update({k: v for k, v in updates.items() if v is not None})
    return state


def set_conversation_key(session_folder: str | Path, conversation_key: str) -> None:
    write_state(session_folder, _merge_state(session_folder, conversationKey=conversation_key))


def set_workspace_path(session_folder: str | Path, workspace_path: str | Path) -> None:
    write_state(
        session_folder,
        _merge_state(session_folder, workspacePath=str(Path(workspace_path).expanduser().resolve())),
    )


def extract_conversation_key(created: Any) -> str:
    """Normalize conversations.create result to main:conversation:<uuid>."""
    if isinstance(created, dict):
        conversation = created.get("conversation")
        candidates = [
            created.get("conversationKey"),
            created.get("activeConversationKey"),
            conversation.get("conversationKey") if isinstance(conversation, dict) else None,
        ]
        session = created.get("session")
        if isinstance(session, dict):
            candidates.append(session.get("activeConversationKey"))
        for raw in candidates:
            key = str(raw or "").strip()
            if key:
                return key
    key = str(created or "").strip()
    if key:
        return key
    raise RuntimeError("conversations.create returned no conversationKey")


def ensure_kimi_work_session(
    session_folder: str | Path,
    *,
    workspace_path: str | Path,
    title: str | None = None,
) -> str:
    """Bind workspace + conversation; batch prep RPCs on one WS when both are needed."""
    folder = session_folder
    resolved = Path(workspace_path).expanduser().resolve()
    existing_key = get_conversation_key(folder)
    if existing_key and not is_usable_conversation_key(existing_key):
        clear_conversation_key(folder)
        existing_key = None
    existing_ws = get_workspace_path(folder)
    need_open = existing_ws != resolved
    need_create = existing_key is None
    if not need_open and not need_create:
        return existing_key  # type: ignore[return-value]

    from agent_lab.kimi.control_client import KimiWorkBridgeUnavailable, rpc, rpc_batch

    if need_open and need_create:
        try:
            results = rpc_batch(
                [
                    ("workspace.openProject", {"path": str(resolved)}),
                    (
                        "conversations.create",
                        {"sessionKey": "main", "title": title or "agent-lab"},
                    ),
                ],
            )
        except KimiWorkBridgeUnavailable:
            from agent_lab.kimi.work_workspace import open_workspace

            open_workspace(resolved)
            created = rpc(
                "conversations.create",
                {"sessionKey": "main", "title": title or "agent-lab"},
            )
            set_workspace_path(folder, resolved)
            key = extract_conversation_key(created)
            set_conversation_key(folder, key)
            return key
        set_workspace_path(folder, resolved)
        key = extract_conversation_key(results[-1])
        set_conversation_key(folder, key)
        return key

    if need_open:
        from agent_lab.kimi.work_workspace import open_workspace

        open_workspace(resolved)
        set_workspace_path(folder, resolved)
    if need_create:
        created = rpc(
            "conversations.create",
            {"sessionKey": "main", "title": title or "agent-lab"},
        )
        key = extract_conversation_key(created)
        set_conversation_key(folder, key)
        return key
    return existing_key  # type: ignore[return-value]


def get_or_create_conversation(session_folder: str | Path, *, title: str | None = None) -> str:
    existing = get_conversation_key(session_folder)
    if existing:
        return existing
    from agent_lab.kimi.control_client import rpc

    created = rpc(
        "conversations.create",
        {"sessionKey": "main", "title": title or "agent-lab"},
    )
    key = extract_conversation_key(created)
    set_conversation_key(session_folder, key)
    return key
