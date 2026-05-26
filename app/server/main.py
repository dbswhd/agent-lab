"""Agent Lab API — FastAPI backend for the web UI."""

from __future__ import annotations

import json
import os
import queue
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

_ROOT = Path(os.getenv("AGENT_LAB_ROOT", Path(__file__).resolve().parents[2]))
_home = Path.home()
for _env_file in (
    Path(os.getenv("DOTENV_PATH", "")),
    _ROOT / ".env",
    _home / "Projects/agent-lab/.env",
    _home / ".agent-lab/.env",
):
    if _env_file.is_file():
        load_dotenv(_env_file)

from agent_lab import codex_cli  # noqa: E402
from agent_lab.invoke import ensure_ready, model_name, provider  # noqa: E402
from agent_lab.agents.registry import available_agents, label as agent_label  # noqa: E402
from agent_lab.attachments import (  # noqa: E402
    MAX_FILE_BYTES,
    MAX_FILES,
    attachments_dir,
    list_attachment_names,
)
from agent_lab.room import continue_room_round, run_room  # noqa: E402
from agent_lab.session import session_dir  # noqa: E402
from agent_lab.runner import provider_override, run_topic_with_progress  # noqa: E402
from agent_lab.session import SESSIONS_DIR  # noqa: E402

app = FastAPI(title="Agent Lab API", version="0.1.0")
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


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "provider": provider() or None,
        "model": model_name() if provider() else None,
        "codex_cli": codex_cli.is_available(),
        "sessions_dir": str(SESSIONS_DIR),
    }


@app.get("/api/agents")
def agents() -> dict[str, Any]:
    ready = available_agents()
    return {
        "agents": [
            {
                "id": aid,
                "label": agent_label(aid),
                "ready": aid in ready,
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


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, Any]:
    folder = SESSIONS_DIR / session_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="session not found")
    shutil.rmtree(folder)
    return {"ok": True, "id": session_id}


@app.post("/api/runs")
def create_run(body: RunRequest) -> dict[str, Any]:
    global _active_run
    topic = body.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic required")

    def generate():
        global _active_run
        if not _run_lock.acquire(blocking=False):
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
            _run_lock.release()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/room/runs")
async def create_room_run(
    topic: str = Form(...),
    agents: str = Form("[]"),
    synthesize: bool = Form(True),
    session_id: str | None = Form(None),
    permissions: str = Form("{}"),
    files: list[UploadFile] = File(default=[]),
) -> StreamingResponse:
    topic = topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic required")

    try:
        agent_ids = json.loads(agents) if agents else []
    except json.JSONDecodeError:
        agent_ids = []
    agent_list = [a.strip().lower() for a in agent_ids if str(a).strip()] or None

    try:
        perm_obj = json.loads(permissions) if permissions else {}
    except json.JSONDecodeError:
        perm_obj = {}

    folder: Path | None = None
    if session_id:
        folder = SESSIONS_DIR / session_id
        if not folder.is_dir():
            raise HTTPException(status_code=404, detail="session not found")
    else:
        folder = session_dir(topic, base=SESSIONS_DIR)
        (folder / "topic.txt").write_text(topic + "\n", encoding="utf-8")

    saved_files = await _save_uploads(folder, files)

    def generate():
        if not _run_lock.acquire(blocking=False):
            yield _sse({"type": "error", "message": "a run is already in progress"})
            return

        event_q: queue.SimpleQueue[dict[str, Any] | None] = queue.SimpleQueue()
        result: dict[str, Any] = {}

        def on_event(typ: str, payload: dict[str, Any]) -> None:
            event_q.put({"type": typ, **payload})

        def worker() -> None:
            try:
                if session_id:
                    _messages, plan_md = continue_room_round(
                        folder,  # type: ignore[arg-type]
                        topic,
                        agents=agent_list,  # type: ignore[arg-type]
                        synthesize=synthesize,
                        on_event=on_event,
                        permissions=perm_obj,
                    )
                    result["folder"] = folder
                    result["plan_md"] = plan_md
                else:
                    f, _messages, plan_md = run_room(
                        topic,
                        agents=agent_list,  # type: ignore[arg-type]
                        synthesize=synthesize,
                        on_event=on_event,
                        session_folder=folder,
                        permissions=perm_obj,
                    )
                    result["folder"] = f
                    result["plan_md"] = plan_md
            except Exception as e:
                result["error"] = e
            finally:
                event_q.put(None)

        try:
            yield _sse(
                {
                    "type": "start",
                    "topic": topic,
                    "workflow": "room.parallel",
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
                raise result["error"]
            out_folder = result["folder"]
            plan_md = result.get("plan_md", "")
            complete = result.get("complete_event") or {}
            yield _sse(
                {
                    "type": "complete",
                    "session_id": complete.get("session_id") or out_folder.name,
                    "plan_preview": plan_md[:500] if plan_md else "",
                }
            )
        except Exception as e:
            yield _sse({"type": "error", "message": str(e)})
        finally:
            _run_lock.release()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
