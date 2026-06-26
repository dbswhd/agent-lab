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
from agent_lab.room_messages import MAX_AGENT_PARALLEL_ROUNDS
from agent_lab.run_observability import observability_snapshot
from agent_lab.session_paths import SESSIONS_DIR

TURN_PROFILES = frozenset(
    {"quick", "team", "loop", "analyze", "discuss", "review", "free", "specialist", "verified", "divergence", "발산"}
)


def room_session_context(folder: Path | None) -> tuple[str, dict[str, Any]]:
    """Lazy re-export so deps.py stays importable without langgraph."""
    from agent_lab.room import _session_context
    return _session_context(folder)


class RunRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=2000)
    backend: str | None = Field(default=None, description="codex | openai | anthropic")


class RoomRunRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=2000)
    agents: list[str] | None = Field(default=None, description="cursor, codex, claude — default: all available")
    synthesize: bool = Field(default=True, description="Scribe plan.md after round")
    session_id: str | None = Field(default=None, description="Continue an existing room session")


class RenameSessionRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200)


class SessionGoalPatchRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    max_checks: int = Field(default=5, ge=1, le=20)


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
    executor: Literal["cursor", "codex"] | None = None
    permissions: dict[str, Any] = Field(default_factory=dict)


class PlanExecuteReviseRequest(BaseModel):
    comment: str = Field(..., min_length=1, max_length=2000)
    chunk_ref: str | None = Field(default=None, max_length=500)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    executor: Literal["cursor", "codex"] | None = None
    permissions: dict[str, Any] = Field(default_factory=dict)


class HumanInboxCreateRequest(BaseModel):
    kind: Literal["question", "build"]
    prompt: str = Field(..., min_length=1, max_length=4000)
    source: str | None = Field(default="manual")
    options: list[dict[str, Any]] = Field(default_factory=list)
    multi_select: bool = False
    action_ref: str | None = None
    summary: str | None = None
    risks: list[str] = Field(default_factory=list)
    human_turn_id: int | None = None
    context_ref: str | None = None


class HumanInboxResolveRequest(BaseModel):
    selected: list[str] | None = None
    decision: Literal["go", "defer", "reject"] | None = None
    note: str | None = None
    status: Literal["resolved", "deferred", "rejected"] | None = None
    append_chat: bool = True


class PlanExecuteIsolationOverrideRequest(BaseModel):
    execution_id: str = Field(..., min_length=1)
    mode: str = Field(..., min_length=1)
    confirmation: str = Field(..., min_length=1)
    permissions: dict[str, Any] = Field(default_factory=dict)


class ClarifierAnswersRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    mark_complete: bool = True


class ExternalHandoffRequest(BaseModel):
    stopped_cleanly: bool
    changed_files: list[str] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    evidence_summary: str = Field(..., min_length=1)
    risks: list[str] = Field(default_factory=list)
    source: str | None = None
    tool_id: str | None = None


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
    root = SESSIONS_DIR
    if not root.is_dir():
        return [], 0

    # Phase 1: walk all dirs, read only meta.json to check archived status.
    # topic.txt and run.json are deferred to Phase 3 to avoid N+1 I/O.
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(root.iterdir(), reverse=True):
        if not path.is_dir() or path.name.startswith("."):
            continue
        meta = read_meta(path)
        if bool(meta.get("archived")) != archived:
            continue
        candidates.append((path, meta))

    total = len(candidates)

    # Phase 2: apply pagination.
    page = candidates[offset : offset + limit] if limit is not None else candidates[offset:]

    # Phase 3: read topic.txt and run.json only for the requested page.
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
        # Read lines as text first — cheap. Parse JSON only for the requested page.
        all_lines = [ln for ln in chat_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        chat_total = len(all_lines)
        page_lines = all_lines[chat_offset : chat_offset + chat_limit] if chat_limit is not None else all_lines[chat_offset:]
        chat = [json.loads(ln) for ln in page_lines]

    run_json: dict[str, Any] = {}
    if (folder / "run.json").is_file():
        run_json = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        gc_stale_worktrees(folder, run_json)

    from agent_lab.room_live_log import read_live_room_log

    live_log = read_live_room_log(folder)

    from agent_lab.cost_ledger import budget_status

    cost = {
        "ledger": run_json.get("cost_ledger") if isinstance(run_json.get("cost_ledger"), dict) else None,
        "budget": budget_status(run_json),
    }

    return {
        "id": session_id,
        "topic": read("topic.txt") or meta.get("topic", ""),
        "plan_md": read("plan.md"),
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
