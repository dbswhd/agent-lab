"""Shared FastAPI request models and session helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, Field

from agent_lab.attachments import (
    MAX_FILE_BYTES,
    MAX_FILES,
    attachments_dir,
    list_attachment_names,
)
from agent_lab.plan_execute_worktree import gc_stale_worktrees
from agent_lab.room import MAX_AGENT_PARALLEL_ROUNDS, _session_context as room_session_context
from agent_lab.session import SESSIONS_DIR

TURN_PROFILES = frozenset({"quick", "analyze", "discuss", "review", "free", "specialist"})


class RunRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=2000)
    backend: str | None = Field(
        default=None, description="codex | openai | anthropic"
    )


class RoomRunRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=2000)
    agents: list[str] | None = Field(
        default=None, description="cursor, codex, claude — default: all available"
    )
    synthesize: bool = Field(default=True, description="Scribe plan.md after round")
    session_id: str | None = Field(
        default=None, description="Continue an existing room session"
    )


class RenameSessionRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200)


class TaskClaimRequest(BaseModel):
    agent: str = Field(..., min_length=1)


class TeamLeadRequest(BaseModel):
    agent: str = Field(..., min_length=1)


class AgentCapabilitiesPatchRequest(BaseModel):
    capabilities: dict[str, Any] = Field(default_factory=dict)


class TaskCompleteRequest(BaseModel):
    artifact_refs: list[str] = Field(default_factory=list)


class ObjectionResolveRequest(BaseModel):
    verdict: Literal["accepted", "wontfix"]
    note: str = ""


class PlanExecuteDryRunRequest(BaseModel):
    action_index: int = Field(..., ge=1)
    action_kind: str | None = Field(
        default=None,
        description="now | roadmap | legacy, or composite key now:1",
    )
    permissions: dict[str, Any] = Field(default_factory=dict)


class PlanExecuteResolveRequest(BaseModel):
    execution_id: str = Field(..., min_length=1)
    vote: str = Field(..., min_length=1)
    permissions: dict[str, Any] = Field(default_factory=dict)


class PlanExecuteMergeRequest(BaseModel):
    execution_id: str = Field(..., min_length=1)


class PlanExecuteReverifyRequest(BaseModel):
    execution_id: str = Field(..., min_length=1)


class PlanExecuteIsolationOverrideRequest(BaseModel):
    execution_id: str = Field(..., min_length=1)
    mode: str = Field(..., min_length=1)
    confirmation: str = Field(..., min_length=1)
    permissions: dict[str, Any] = Field(default_factory=dict)


class ContextPreviewRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    agent: str = Field(..., min_length=1)
    parallel_round: int = Field(default=1, ge=1, le=MAX_AGENT_PARALLEL_ROUNDS)
    review_mode: bool = False
    efficiency_mode: bool = False
    slim_context: bool = False
    permissions: dict[str, Any] = Field(default_factory=dict)
    agents: list[str] | None = None


def session_folder_or_404(session_id: str) -> Path:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    return folder


async def save_uploads(folder: Path, files: list[UploadFile]) -> list[str]:
    if len(files) > MAX_FILES:
        raise HTTPException(
            status_code=400, detail=f"max {MAX_FILES} files per message"
        )
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


def list_sessions(*, archived: bool = False) -> list[dict[str, Any]]:
    root = SESSIONS_DIR
    if not root.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(root.iterdir(), reverse=True):
        if not path.is_dir() or path.name.startswith("."):
            continue
        meta = read_meta(path)
        is_archived = bool(meta.get("archived"))
        if is_archived != archived:
            continue
        topic_file = path / "topic.txt"
        topic = (
            topic_file.read_text(encoding="utf-8").strip()
            if topic_file.is_file()
            else meta.get("topic", path.name)
        )
        items.append(
            {
                "id": path.name,
                "topic": topic,
                "created_at": meta.get("created_at"),
                "model": meta.get("model"),
                "archived": is_archived,
                "workflow": meta.get("workflow"),
                "workspace_preset": meta.get("workspace_preset"),
                "session_template": meta.get("session_template"),
                "workspace_label": meta.get("workspace_label"),
                "path": str(path),
            }
        )
    return items


def session_detail(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)

    def read(name: str) -> str:
        p = folder / name
        return p.read_text(encoding="utf-8") if p.is_file() else ""

    meta = read_meta(folder)

    chat: list[dict[str, Any]] = []
    chat_path = folder / "chat.jsonl"
    if chat_path.is_file():
        for line in chat_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                chat.append(json.loads(line))

    run_json: dict[str, Any] = {}
    if (folder / "run.json").is_file():
        run_json = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        gc_stale_worktrees(folder, run_json)

    return {
        "id": session_id,
        "topic": read("topic.txt") or meta.get("topic", ""),
        "plan_md": read("plan.md"),
        "transcript_md": read("transcript.md"),
        "meta": meta,
        "chat": chat,
        "run": run_json,
        "attachments": list_attachment_names(folder),
    }


def archive_meta(folder: Path) -> dict[str, Any]:
    meta = read_meta(folder)
    meta["archived"] = True
    meta["archived_at"] = meta.get("archived_at") or datetime.now(
        timezone.utc
    ).isoformat()
    write_meta(folder, meta)
    return meta


def sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
