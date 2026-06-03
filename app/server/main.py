"""Agent Lab API — FastAPI backend for the web UI."""

from __future__ import annotations

import json
import os
import queue
import shutil
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

_ROOT = Path(os.getenv("AGENT_LAB_ROOT", Path(__file__).resolve().parents[2]))
_home = Path.home()

from agent_lab.app_config import apply_config_env  # noqa: E402
from agent_lab.app_logging import setup_app_logging  # noqa: E402

apply_config_env()

for _env_file in (
    Path(os.getenv("DOTENV_PATH", "")),
    _ROOT / ".env",
    _home / "Projects/agent-lab/.env",
    _home / ".agent-lab/.env",
):
    if _env_file.is_file():
        load_dotenv(_env_file)

from agent_lab import codex_cli
from agent_lab import claude_cli  # noqa: E402
from agent_lab.invoke import ensure_ready, model_name, provider  # noqa: E402
from agent_lab.agents.registry import (  # noqa: E402
    available_agents,
    label as agent_label,
    model_label as agent_model_label,
)
from agent_lab.attachments import (  # noqa: E402
    MAX_FILE_BYTES,
    MAX_FILES,
    attachments_dir,
    list_attachment_names,
)
from agent_lab.room import (  # noqa: E402
    DEFAULT_AGENT_PARALLEL_ROUNDS,
    MAX_AGENT_PARALLEL_ROUNDS,
    continue_room_round,
    preview_agent_payload,
    run_room,
    synthesize_session_plan,
    load_session_messages,
    _session_context as room_session_context,
)
from agent_lab.agent_health import build_health_payload, reconnect_cursor_bridge  # noqa: E402
from agent_lab.api_diagnostics import build_diagnostics_payload  # noqa: E402
from agent_lab.agent_preflight import agents_not_ready, build_agent_preflight  # noqa: E402
from agent_lab.run_control import (  # noqa: E402
    end_run,
    force_reset_run_lock,
    maybe_release_orphaned_run_lock,
    request_cancel,
    run_lock_status,
    try_begin_run,
)
from agent_lab.room_consensus import (  # noqa: E402
    max_consensus_calls,
    max_consensus_rounds,
)
from agent_lab.context_limits import efficiency_mode_default  # noqa: E402
from agent_lab.session import SESSIONS_DIR, session_dir  # noqa: E402
from agent_lab.runner import provider_override, run_topic_with_progress  # noqa: E402
from agent_lab.plan_execute import (  # noqa: E402
    abort_merge_execution,
    confirm_merge_execution,
    list_plan_actions,
    resolve_execution,
    run_dry_run,
    run_isolation_override,
)
from agent_lab.plan_execute_worktree import WorktreeUnavailable, gc_stale_worktrees  # noqa: E402
from agent_lab.plan_pending import (  # noqa: E402
    PlanSnapshotRequired,
    approve_pending_plan,
    pending_plans_public_payload,
    reject_pending_plan,
)
from agent_lab.room_hooks import PreExecuteBlocked  # noqa: E402
from agent_lab.room_objections import ObjectionBlocksExecute  # noqa: E402
from agent_lab.session_setup import (  # noqa: E402
    merge_setup_permissions,
    seed_session_setup,
    session_setup_options,
)
TURN_PROFILES = frozenset({"quick", "analyze", "discuss", "review", "free", "specialist"})

setup_app_logging()


def _api_startup() -> None:
    from agent_lab.app_logging import write_boot_line

    try:
        payload = build_diagnostics_payload()
        write_boot_line(
            "uvicorn startup pid=%s port=%s sessions=%s"
            % (payload["pid"], payload["port"], payload["sessions_dir"])
        )
    except Exception as exc:
        write_boot_line(f"uvicorn startup diagnostics failed: {exc}")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _api_startup()
    yield


app = FastAPI(title="Agent Lab API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:1420",
        "http://localhost:1420",
        "tauri://localhost",
        "https://tauri.localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_run_lock = threading.Lock()
_active_run = False
# Room/classic worker runs use agent_lab.run_control.try_begin_run / end_run.


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


async def _save_uploads(folder: Path, files: list[UploadFile]) -> list[str]:
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


def _read_meta(folder: Path) -> dict[str, Any]:
    meta_path = folder / "meta.json"
    if not meta_path.is_file():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_meta(folder: Path, meta: dict[str, Any]) -> None:
    (folder / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _list_sessions(*, archived: bool = False) -> list[dict[str, Any]]:
    root = SESSIONS_DIR
    if not root.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(root.iterdir(), reverse=True):
        if not path.is_dir() or path.name.startswith("."):
            continue
        meta = _read_meta(path)
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


def _session_detail(session_id: str) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")

    def read(name: str) -> str:
        p = folder / name
        return p.read_text(encoding="utf-8") if p.is_file() else ""

    meta = _read_meta(folder)

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


@app.get("/api/session-setup/options")
def get_session_setup_options() -> dict[str, Any]:
    return session_setup_options()


@app.get("/api/health")
def health(
    probe_bridge: bool = False,
    probe_preflight: bool = False,
    session_id: str | None = None,
) -> dict[str, Any]:
    run_meta: dict[str, Any] | None = None
    if session_id:
        folder = SESSIONS_DIR / session_id
        if folder.is_dir():
            _plan_md, run_meta = room_session_context(folder)
    return build_health_payload(
        probe_bridge=probe_bridge,
        probe_preflight=probe_preflight,
        run_meta=run_meta,
    )


@app.get("/api/agents/preflight")
def agents_preflight() -> dict[str, Any]:
    agents = build_agent_preflight(probe_bridge=True, probe_cli=True)
    return {
        "ok": all(a.get("ready") for a in agents),
        "agents": agents,
    }


@app.get("/api/diagnostics")
def diagnostics() -> dict[str, Any]:
    return build_diagnostics_payload()


@app.post("/api/health/reconnect-cursor")
def health_reconnect_cursor() -> dict[str, Any]:
    return reconnect_cursor_bridge()


@app.get("/api/agents")
def agents() -> dict[str, Any]:
    ready = available_agents()
    return {
        "agents": [
            {
                "id": aid,
                "label": agent_label(aid),
                "ready": aid in ready,
                "model": agent_model_label(aid),
            }
            for aid in ("cursor", "codex", "claude")
        ],
        "default": ready,
    }


@app.get("/api/backends")
def backends() -> dict[str, Any]:
    options = []
    if codex_cli.is_available():
        options.append(
            {
                "id": "codex",
                "label": "Codex (ChatGPT Plus)",
                "ready": True,
            }
        )
    if claude_cli.is_available():
        options.append(
            {
                "id": "claude_code",
                "label": "Claude Code (subscription)",
                "ready": True,
            }
        )
    if os.getenv("OPENAI_API_KEY"):
        options.append({"id": "openai", "label": "OpenAI API", "ready": True})
    if os.getenv("ANTHROPIC_API_KEY"):
        options.append(
            {"id": "anthropic", "label": "Anthropic API", "ready": True}
        )
    return {
        "default": provider() or (options[0]["id"] if options else None),
        "options": options,
    }


@app.get("/api/sessions")
def sessions(archived: bool = False) -> dict[str, Any]:
    return {"sessions": _list_sessions(archived=archived)}


@app.post("/api/sessions/{session_id}/archive")
def archive_session(session_id: str) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    meta = _read_meta(folder)
    meta["archived"] = True
    meta["archived_at"] = meta.get("archived_at") or datetime.now(
        timezone.utc
    ).isoformat()
    _write_meta(folder, meta)
    return {"ok": True, "id": session_id, "archived": True}


@app.post("/api/sessions/{session_id}/unarchive")
def unarchive_session(session_id: str) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    meta = _read_meta(folder)
    meta["archived"] = False
    meta.pop("archived_at", None)
    _write_meta(folder, meta)
    return {"ok": True, "id": session_id, "archived": False}


@app.get("/api/sessions/{session_id}")
def session(session_id: str) -> dict[str, Any]:
    return _session_detail(session_id)


@app.patch("/api/sessions/{session_id}")
def rename_session(session_id: str, body: RenameSessionRequest) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    topic = body.topic.strip()
    (folder / "topic.txt").write_text(topic + "\n", encoding="utf-8")
    meta = _read_meta(folder)
    meta["topic"] = topic
    _write_meta(folder, meta)
    return {"ok": True, "id": session_id, "topic": topic}


@app.get("/api/sessions/{session_id}/tasks")
def session_tasks(session_id: str) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    _plan_md, run_meta = room_session_context(folder)
    from agent_lab.room_tasks import tasks_public_payload

    return tasks_public_payload(run_meta)


@app.post("/api/sessions/{session_id}/tasks/{task_id}/claim")
def claim_session_task(
    session_id: str,
    task_id: str,
    body: TaskClaimRequest,
) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    from agent_lab.room_tasks import claim_task, tasks_public_payload

    _plan_md, run_meta = room_session_context(folder)
    try:
        task = claim_task(run_meta, task_id, body.agent.strip().lower())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    (folder / "run.json").write_text(
        json.dumps(run_meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"ok": True, "task": task, **tasks_public_payload(run_meta)}


@app.post("/api/sessions/{session_id}/tasks/{task_id}/complete")
def complete_session_task(
    session_id: str,
    task_id: str,
    body: TaskCompleteRequest | None = None,
) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    from agent_lab.room_tasks import complete_task, tasks_public_payload

    _plan_md, run_meta = room_session_context(folder)
    run_meta["_session_folder"] = str(folder.resolve())
    run_meta["_session_id"] = session_id
    refs = list((body.artifact_refs if body else None) or [])
    try:
        task = complete_task(run_meta, task_id, artifact_refs=refs or None)
    except ValueError as e:
        msg = str(e)
        status = 409 if "승인" in msg or "검증" in msg or "실행" in msg else 400
        raise HTTPException(status_code=status, detail=msg) from e
    from agent_lab.run_meta import persist_run_meta

    (folder / "run.json").write_text(
        json.dumps(persist_run_meta(run_meta), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"ok": True, "task": task, **tasks_public_payload(run_meta)}


class ObjectionResolveRequest(BaseModel):
    verdict: Literal["accepted", "wontfix"]
    note: str = ""


@app.post("/api/sessions/{session_id}/objections/{objection_id}/resolve")
def resolve_session_objection(
    session_id: str,
    objection_id: str,
    body: ObjectionResolveRequest,
) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    from agent_lab.room_objections import resolve_objection
    from agent_lab.room_tasks import tasks_public_payload

    _plan_md, run_meta = room_session_context(folder)
    try:
        row = resolve_objection(
            run_meta,
            objection_id,
            verdict=body.verdict,
            note=body.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    from agent_lab.run_meta import persist_run_meta

    (folder / "run.json").write_text(
        json.dumps(persist_run_meta(run_meta), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"ok": True, "objection": row, **tasks_public_payload(run_meta)}


@app.get("/api/sessions/{session_id}/agent-capabilities")
def get_session_agent_capabilities(
    session_id: str,
    permissions: str | None = None,
) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    _plan_md, run_meta = room_session_context(folder)
    perm_obj: dict[str, Any] = {}
    if permissions:
        try:
            perm_obj = json.loads(permissions)
        except json.JSONDecodeError:
            perm_obj = {}
    from agent_lab.room_agent_capabilities import capabilities_public_payload

    return {"ok": True, **capabilities_public_payload(run_meta, perm_obj)}


@app.patch("/api/sessions/{session_id}/agent-capabilities")
def patch_session_agent_capabilities(
    session_id: str,
    body: AgentCapabilitiesPatchRequest,
) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    from agent_lab.room_agent_capabilities import (
        capabilities_public_payload,
        write_agent_capabilities,
    )
    from agent_lab.run_meta import persist_run_meta

    _plan_md, run_meta = room_session_context(folder)
    caps_in = body.capabilities if isinstance(body.capabilities, dict) else {}
    write_agent_capabilities(run_meta, caps_in, mark_custom=True)
    (folder / "run.json").write_text(
        json.dumps(persist_run_meta(run_meta), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"ok": True, **capabilities_public_payload(run_meta)}


@app.patch("/api/sessions/{session_id}/team-lead")
def set_session_team_lead(
    session_id: str,
    body: TeamLeadRequest,
) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    from agent_lab.room_tasks import set_team_lead_agent, tasks_public_payload

    _plan_md, run_meta = room_session_context(folder)
    lead = set_team_lead_agent(run_meta, body.agent.strip().lower())
    (folder / "run.json").write_text(
        json.dumps(run_meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"ok": True, "team_lead": lead, **tasks_public_payload(run_meta)}


@app.get("/api/sessions/{session_id}/plan-actions")
def session_plan_actions(
    session_id: str,
    permissions: str | None = None,
) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    perms: dict[str, Any] = {}
    if permissions:
        try:
            perms = json.loads(permissions)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail="invalid permissions JSON") from e
    return list_plan_actions(folder, permissions=perms)


@app.get("/api/sessions/{session_id}/execute/pending-plans")
def session_pending_plans(session_id: str) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    _plan_md, run_meta = room_session_context(folder)
    return {"ok": True, **pending_plans_public_payload(run_meta)}


@app.post("/api/sessions/{session_id}/execute/pending-plans/{pending_id}/approve")
def session_approve_pending_plan(
    session_id: str,
    pending_id: str,
) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    try:
        row = approve_pending_plan(folder, pending_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _plan_md, run_meta = room_session_context(folder)
    return {
        "ok": True,
        "pending_plan": row,
        **pending_plans_public_payload(run_meta),
    }


@app.post("/api/sessions/{session_id}/execute/pending-plans/{pending_id}/reject")
def session_reject_pending_plan(
    session_id: str,
    pending_id: str,
) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    try:
        row = reject_pending_plan(folder, pending_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _plan_md, run_meta = room_session_context(folder)
    return {
        "ok": True,
        "pending_plan": row,
        **pending_plans_public_payload(run_meta),
    }


@app.post("/api/sessions/{session_id}/execute/dry-run")
def session_execute_dry_run(
    session_id: str,
    body: PlanExecuteDryRunRequest,
) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    try:
        execution = run_dry_run(
            folder,
            action_index=body.action_index,
            action_kind=body.action_kind,
            permissions=body.permissions,
        )
    except PlanSnapshotRequired as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "plan_snapshot_required",
                "message": "plan 스냅샷 승인 후 dry-run 할 수 있습니다.",
                "pending_plan": e.pending_plan,
            },
        ) from e
    except WorktreeUnavailable as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": e.reason,
                "message": str(e),
                "execution_id": e.execution_id,
                "remediation": ["fix_git_worktree_and_retry"],
            },
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ObjectionBlocksExecute as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "open_objection",
                "message": str(e),
                "objections": e.objections,
            },
        ) from e
    except PreExecuteBlocked as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "pre_execute_blocked",
                "message": str(e),
                "pre_verify": e.pre_verify,
            },
        ) from e
    return {"ok": True, "execution": execution}


@app.post("/api/sessions/{session_id}/execute/isolation/override")
def session_execute_isolation_override(
    session_id: str,
    body: PlanExecuteIsolationOverrideRequest,
) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    try:
        execution = run_isolation_override(
            folder,
            execution_id=body.execution_id.strip(),
            mode=body.mode,
            confirmation=body.confirmation,
            permissions=body.permissions,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, "execution": execution}


@app.post("/api/sessions/{session_id}/execute/resolve")
def session_execute_resolve(
    session_id: str,
    body: PlanExecuteResolveRequest,
) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    try:
        result = resolve_execution(
            folder,
            execution_id=body.execution_id.strip(),
            vote=body.vote,
            permissions=body.permissions,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **result}


@app.post("/api/sessions/{session_id}/execute/merge/abort")
def session_execute_merge_abort(
    session_id: str,
    body: PlanExecuteMergeRequest,
) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    try:
        result = abort_merge_execution(
            folder,
            execution_id=body.execution_id.strip(),
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"ok": True, **result}


@app.post("/api/sessions/{session_id}/execute/merge/confirm")
def session_execute_merge_confirm(
    session_id: str,
    body: PlanExecuteMergeRequest,
) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    try:
        result = confirm_merge_execution(
            folder,
            execution_id=body.execution_id.strip(),
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"ok": True, **result}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    shutil.rmtree(folder)
    return {"ok": True, "id": session_id}


@app.post("/api/room/context-preview")
def room_context_preview(body: ContextPreviewRequest) -> dict[str, Any]:
    folder = SESSIONS_DIR / body.session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    agent = body.agent.strip().lower()
    if agent not in ("cursor", "codex", "claude"):
        raise HTTPException(status_code=400, detail="agent must be cursor, codex, or claude")
    agent_list: list[str] | None = None
    if body.agents:
        agent_list = [a.strip().lower() for a in body.agents if str(a).strip()]
    try:
        payload, bundle = preview_agent_payload(
            folder,
            agent,  # type: ignore[arg-type]
            agents=agent_list,  # type: ignore[arg-type]
            parallel_round=body.parallel_round,
            permissions=body.permissions,
            review_mode=body.review_mode,
            efficiency_mode=body.efficiency_mode,
            slim_context=body.slim_context,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session not found") from None
    return {
        "session_id": body.session_id,
        "agent": agent,
        "parallel_round": body.parallel_round,
        "review_mode": body.review_mode,
        "payload": payload,
        "chars": len(payload),
        "meta": bundle.meta.to_dict(),
        "limits": all_limits_for_api(),
    }


@app.post("/api/runs")
def create_run(body: RunRequest) -> dict[str, Any]:
    global _active_run
    topic = body.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic required")

    def generate():
        global _active_run
        if not try_begin_run():
            maybe_release_orphaned_run_lock()
            if not try_begin_run():
                yield _sse({"type": "error", "message": "a run is already in progress"})
                return

        _active_run = True
        events: list[dict[str, Any]] = []

        def on_step(node: str, status: str, extra: dict | None = None):
            events.append(
                {
                    "type": "step",
                    "node": node,
                    "status": status,
                    "extra": extra or {},
                }
            )

        try:
            with provider_override(body.backend):
                try:
                    ensure_ready()
                except RuntimeError as e:
                    yield _sse({"type": "error", "message": str(e)})
                    return
            yield _sse({"type": "start", "topic": topic, "backend": body.backend})
            state, folder = run_topic_with_progress(
                topic, on_step=on_step, backend=body.backend
            )
            for ev in events:
                yield _sse(ev)
            session_id = Path(folder).name
            yield _sse(
                {
                    "type": "complete",
                    "session_id": session_id,
                    "events": events,
                    "plan_preview": state["plan_md"][:500],
                }
            )
        except Exception as e:
            yield _sse({"type": "error", "message": str(e), "events": events})
        finally:
            _active_run = False
            end_run()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/room/runs")
async def create_room_run(
    topic: str = Form(...),
    agents: str = Form("[]"),
    synthesize: bool | None = Form(None),
    mode: str = Form("discuss"),
    synthesize_only: bool = Form(False),
    agent_rounds: int = Form(DEFAULT_AGENT_PARALLEL_ROUNDS),
    session_id: str | None = Form(None),
    request_id: str | None = Form(None),
    permissions: str = Form("{}"),
    review_mode: bool = Form(False),
    consensus_mode: bool = Form(False),
    efficiency_mode: bool = Form(False),
    turn_profile: str = Form("discuss"),
    research_mode: bool = Form(False),
    workspace_id: str = Form("agent-lab"),
    workspace_path: str | None = Form(None),
    session_template: str = Form("general"),
    agent_capabilities: str = Form("{}"),
    files: list[UploadFile] = File(default=[]),
) -> StreamingResponse:
    topic = topic.strip()
    mode_norm = (mode or "discuss").strip().lower()
    if mode_norm not in ("discuss", "plan"):
        raise HTTPException(status_code=400, detail="mode must be discuss or plan")
    if synthesize is None:
        synthesize = mode_norm == "plan"
    if synthesize_only and not session_id:
        raise HTTPException(
            status_code=400, detail="synthesize_only requires session_id"
        )
    if not synthesize_only and not topic:
        raise HTTPException(status_code=400, detail="topic required")

    try:
        agent_ids = json.loads(agents) if agents else []
    except json.JSONDecodeError:
        agent_ids = []
    agent_list = [a.strip().lower() for a in agent_ids if str(a).strip()] or None

    if not synthesize_only and agent_list:
        bad = agents_not_ready(agent_list)
        if bad:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "agents not ready",
                    "agents": bad,
                },
            )

    try:
        perm_obj = json.loads(permissions) if permissions else {}
    except json.JSONDecodeError:
        perm_obj = {}

    workspace_norm = (workspace_id or "agent-lab").strip().lower()
    workspace_path_norm = (workspace_path or "").strip() or None
    template_norm = (session_template or "general").strip().lower()
    perm_obj = merge_setup_permissions(
        perm_obj,
        workspace_norm,
        workspace_path_norm,
    )

    caps_obj: dict[str, Any] = {}
    try:
        parsed_caps = json.loads(agent_capabilities) if agent_capabilities else {}
        if isinstance(parsed_caps, dict):
            caps_obj = parsed_caps
    except json.JSONDecodeError:
        caps_obj = {}

    folder: Path | None = None
    if session_id:
        folder = SESSIONS_DIR / session_id
        if not folder.is_dir():
            raise HTTPException(status_code=404, detail="session not found")
    else:
        folder = session_dir(topic, base=SESSIONS_DIR)
        (folder / "topic.txt").write_text(topic + "\n", encoding="utf-8")
        try:
            seed_session_setup(
                folder,
                workspace_id=workspace_norm,
                session_template=template_norm,
                workspace_path=workspace_path_norm,
                topic=topic,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    if caps_obj:
        from agent_lab.room_agent_capabilities import write_agent_capabilities

        _plan_md, run_meta = room_session_context(folder)
        write_agent_capabilities(run_meta, caps_obj, mark_custom=True)
        from agent_lab.run_meta import persist_run_meta

        (folder / "run.json").write_text(
            json.dumps(persist_run_meta(run_meta), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    saved_files = await _save_uploads(folder, files)
    parallel_rounds = max(1, min(agent_rounds, MAX_AGENT_PARALLEL_ROUNDS))
    # Align with UI turn profiles: discuss=1, review>=2 (non-UI callers may omit agent_rounds).
    if review_mode and not consensus_mode and parallel_rounds < 2:
        parallel_rounds = 2
    use_efficiency = efficiency_mode or efficiency_mode_default()
    profile_norm = (turn_profile or "analyze").strip().lower()
    if profile_norm == "discuss":
        profile_norm = "analyze"
    if profile_norm not in TURN_PROFILES:
        profile_norm = "analyze"

    def generate():
        event_q: queue.SimpleQueue[dict[str, Any] | None] = queue.SimpleQueue()
        result: dict[str, Any] = {}

        def on_event(typ: str, payload: dict[str, Any]) -> None:
            event_q.put({"type": typ, **payload})

        def worker() -> None:
            if not try_begin_run():
                maybe_release_orphaned_run_lock()
                if not try_begin_run():
                    event_q.put(
                        {
                            "type": "error",
                            "message": "a run is already in progress",
                        }
                    )
                    event_q.put(None)
                    return
            try:
                if synthesize_only and session_id:
                    plan_md, _summary = synthesize_session_plan(
                        folder,  # type: ignore[arg-type]
                        on_event=on_event,
                        permissions=perm_obj,
                        request_id=(request_id or "").strip() or None,
                    )
                    result["folder"] = folder
                    result["plan_md"] = plan_md
                elif session_id:
                    _messages, plan_md = continue_room_round(
                        folder,  # type: ignore[arg-type]
                        topic,
                        agents=agent_list,  # type: ignore[arg-type]
                        synthesize=synthesize,
                        parallel_rounds=parallel_rounds,
                        on_event=on_event,
                        permissions=perm_obj,
                        review_mode=review_mode,
                        consensus_mode=consensus_mode,
                        efficiency_mode=use_efficiency,
                        turn_profile=profile_norm,
                        research_mode=research_mode,
                    )
                    result["folder"] = folder
                    result["plan_md"] = plan_md
                else:
                    f, _messages, plan_md = run_room(
                        topic,
                        agents=agent_list,  # type: ignore[arg-type]
                        synthesize=synthesize,
                        parallel_rounds=parallel_rounds,
                        on_event=on_event,
                        session_folder=folder,
                        permissions=perm_obj,
                        review_mode=review_mode,
                        consensus_mode=consensus_mode,
                        efficiency_mode=use_efficiency,
                        turn_profile=profile_norm,
                        research_mode=research_mode,
                    )
                    result["folder"] = f
                    result["plan_md"] = plan_md
            except Exception as e:
                result["error"] = e
            finally:
                end_run()
                event_q.put(None)

        try:
            yield _sse(
                {
                    "type": "start",
                    "topic": topic,
                    "session_id": folder.name if folder else None,
                    "workflow": "room.parallel",
                    "mode": mode_norm,
                    "synthesize": synthesize,
                    "synthesize_only": synthesize_only,
                    "request_id": (request_id or "").strip() or None,
                    "agent_rounds": parallel_rounds,
                    "review_mode": review_mode,
                    "consensus_mode": consensus_mode,
                    "efficiency_mode": use_efficiency,
                    "turn_profile": profile_norm,
                    "workspace_id": workspace_norm,
                    "session_template": template_norm,
                    "attachments": saved_files,
                }
            )
            threading.Thread(target=worker, daemon=True).start()
            while True:
                ev = event_q.get()
                if ev is None:
                    break
                if ev.get("type") == "complete":
                    result["complete_event"] = ev
                    continue
                yield _sse(ev)
            if "error" in result:
                err = result["error"]
                yield _sse({"type": "run_failed", "message": str(err)})
                yield _sse({"type": "error", "message": str(err)})
                return
            if "folder" not in result:
                yield _sse(
                    {
                        "type": "run_failed",
                        "message": "room run ended without result",
                    }
                )
                yield _sse(
                    {
                        "type": "error",
                        "message": "room run ended without result",
                    }
                )
                return
            out_folder = result["folder"]
            plan_md = result.get("plan_md", "")
            complete = result.get("complete_event") or {}
            yield _sse(
                {
                    "type": "complete",
                    "session_id": complete.get("session_id") or out_folder.name,
                    "plan_preview": plan_md[:500] if plan_md else "",
                    "status": complete.get("status") or "completed",
                    "failed_agents": complete.get("failed_agents") or [],
                    "succeeded_agents": complete.get("succeeded_agents") or [],
                    "send_receipt": complete.get("send_receipt"),
                    "turn_index": complete.get("turn_index"),
                }
            )
        except Exception as e:
            yield _sse({"type": "error", "message": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/room/run-lock")
def room_run_lock() -> dict[str, Any]:
    return {"ok": True, **run_lock_status()}


@app.post("/api/room/runs/cancel")
def cancel_room_run() -> dict[str, Any]:
    request_cancel()
    released = maybe_release_orphaned_run_lock()
    return {"ok": True, "released_stale_lock": released, **run_lock_status()}


@app.post("/api/room/runs/release-lock")
def release_room_run_lock() -> dict[str, Any]:
    released = maybe_release_orphaned_run_lock()
    status = run_lock_status()
    if status.get("locked"):
        force_reset_run_lock()
        released = True
        status = run_lock_status()
    return {"ok": True, "released": released, **status}


@app.post("/api/sessions/{session_id}/attachments")
async def upload_attachments(
    session_id: str,
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    saved = await _save_uploads(folder, files)
    return {"ok": True, "saved": saved, "attachments": list_attachment_names(folder)}


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


_WEB_DIST = _ROOT / "web" / "dist"
if _WEB_DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(_WEB_DIST), html=True), name="web")
