"""Session path helpers and detail loaders for FastAPI routes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile

from agent_lab.attachments import (
    MAX_FILE_BYTES,
    MAX_FILES,
    attachments_dir,
    list_attachment_names,
)
from agent_lab.plan.execute_worktree import gc_stale_worktrees
from agent_lab.run.observability import observability_snapshot
from agent_lab.session.paths import SESSIONS_DIR  # noqa: F401 — test monkeypatch surface


def room_session_context(folder: Path | None) -> tuple[str, dict[str, Any]]:
    """Session plan/run snapshot — direct submodule import (F9 facade)."""
    from agent_lab.room.session_persist import session_context

    return session_context(folder)


def _sessions_root() -> Path:
    from agent_lab.session.paths import active_sessions_dir

    return active_sessions_dir()


def session_folder_or_404(session_id: str) -> Path:
    folder = _sessions_root() / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    return folder


async def save_uploads(folder: Path, files: list[UploadFile]) -> list[str]:
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"max {MAX_FILES} files per message")
    dest = attachments_dir(folder)
    saved: list[str] = []
    for uf in files:
        if not uf.filename:
            continue
        name = Path(uf.filename).name
        if not name or name.startswith("."):
            continue
        data = await uf.read()
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"{name} exceeds {MAX_FILE_BYTES // (1024 * 1024)}MB limit",
            )
        (dest / name).write_bytes(data)
        saved.append(name)
    return saved


def read_meta(folder: Path) -> dict[str, Any]:
    meta_path = folder / "meta.json"
    if not meta_path.is_file():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_meta(folder: Path, meta: dict[str, Any]) -> None:
    (folder / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def list_sessions(
    *,
    archived: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    root = _sessions_root()
    if not root.is_dir():
        return [], 0

    candidates: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(root.iterdir(), reverse=True):
        if not path.is_dir() or path.name.startswith("."):
            continue
        meta = read_meta(path)
        if bool(meta.get("archived")) != archived:
            continue
        candidates.append((path, meta))

    total = len(candidates)
    page = candidates[offset : offset + limit] if limit is not None else candidates[offset:]

    items: list[dict[str, Any]] = []
    for path, meta in page:
        topic_file = path / "topic.txt"
        topic = topic_file.read_text(encoding="utf-8").strip() if topic_file.is_file() else meta.get("topic", path.name)
        agents: list[str] = []
        workspace_path: str | None = None
        run_path = path / "run.json"
        if run_path.is_file():
            try:
                run_json = json.loads(run_path.read_text(encoding="utf-8"))
                raw_agents = run_json.get("agents")
                if isinstance(raw_agents, list):
                    agents = [str(a) for a in raw_agents if a]
                elif run_json.get("turns"):
                    last_turn = run_json["turns"][-1]
                    if isinstance(last_turn, dict) and isinstance(last_turn.get("agents"), list):
                        agents = [str(a) for a in last_turn["agents"] if a]
                binding = run_json.get("workspace_binding")
                if isinstance(binding, dict) and binding.get("path"):
                    workspace_path = str(binding["path"])
            except (json.JSONDecodeError, OSError, IndexError, KeyError):
                pass
        items.append(
            {
                "id": path.name,
                "topic": topic,
                "created_at": meta.get("created_at"),
                "model": meta.get("model"),
                "archived": bool(meta.get("archived")),
                "workflow": meta.get("workflow"),
                "workspace_preset": meta.get("workspace_preset"),
                "session_template": meta.get("session_template"),
                "workspace_label": meta.get("workspace_label"),
                "agents": agents,
                "workspace_path": workspace_path,
                "path": str(path),
            }
        )
    return items, total


def _read_chat_page(
    chat_path: Path,
    *,
    chat_limit: int | None,
    chat_offset: int,
) -> tuple[list[dict[str, Any]], int]:
    if chat_offset < 0 or (chat_limit is not None and chat_limit < 0):
        all_lines = [line for line in chat_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        page_lines = (
            all_lines[chat_offset : chat_offset + chat_limit] if chat_limit is not None else all_lines[chat_offset:]
        )
        return [json.loads(line) for line in page_lines], len(all_lines)

    chat: list[dict[str, Any]] = []
    chat_total = 0
    with chat_path.open(encoding="utf-8") as chat_file:
        for line in chat_file:
            if not line.strip():
                continue
            if chat_total >= chat_offset and (chat_limit is None or len(chat) < chat_limit):
                chat.append(json.loads(line))
            chat_total += 1
    return chat, chat_total


def session_detail(
    session_id: str,
    *,
    chat_limit: int | None = None,
    chat_offset: int = 0,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)

    def read(name: str) -> str:
        p = folder / name
        return p.read_text(encoding="utf-8") if p.is_file() else ""

    meta = read_meta(folder)

    chat: list[dict[str, Any]] = []
    chat_total = 0
    chat_path = folder / "chat.jsonl"
    if chat_path.is_file():
        chat, chat_total = _read_chat_page(
            chat_path,
            chat_limit=chat_limit,
            chat_offset=chat_offset,
        )

    run_json: dict[str, Any] = {}
    if (folder / "run.json").is_file():
        run_json = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        gc_stale_worktrees(folder, run_json)

    from agent_lab.room.live_log import read_session_live_log

    live_log = read_session_live_log(folder)

    from agent_lab.cost_ledger import budget_status

    cost = {
        "ledger": run_json.get("cost_ledger") if isinstance(run_json.get("cost_ledger"), dict) else None,
        "budget": budget_status(run_json),
    }

    def _read_plan_md(session_folder: Path) -> str:
        from agent_lab.plan.paths import read_session_plan_md

        return read_session_plan_md(session_folder, run_json)

    return {
        "id": session_id,
        "topic": read("topic.txt") or meta.get("topic", ""),
        "plan_md": _read_plan_md(folder),
        "transcript_md": read("transcript.md"),
        "meta": meta,
        "chat": chat,
        "chat_total": chat_total,
        "live_log": live_log,
        "run": run_json,
        "cost": cost,
        "attachments": list_attachment_names(folder),
        "observability": observability_snapshot(run_json, folder=folder),
    }


def archive_meta(folder: Path) -> dict[str, Any]:
    meta = read_meta(folder)
    meta["archived"] = True
    meta["archived_at"] = meta.get("archived_at") or datetime.now(timezone.utc).isoformat()
    write_meta(folder, meta)
    return meta


def sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
