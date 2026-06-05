"""Agent Lab API — FastAPI backend for the web UI."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

from agent_lab.api_diagnostics import build_diagnostics_payload  # noqa: E402
from agent_lab.agent_preflight import agents_not_ready  # noqa: E402
from app.server.deps import (  # noqa: E402
    AgentCapabilitiesPatchRequest,
    ContextPreviewRequest,
    ObjectionResolveRequest,
    PlanExecuteDryRunRequest,
    PlanExecuteIsolationOverrideRequest,
    PlanExecuteMergeRequest,
    PlanExecuteResolveRequest,
    RenameSessionRequest,
    RoomRunRequest,
    RunRequest,
    TaskClaimRequest,
    TaskCompleteRequest,
    TeamLeadRequest,
)
from app.server.routers import (  # noqa: E402
    agents,
    commands,
    health,
    plan_execute,
    room,
    session_governance,
    session_tasks,
    sessions,
)

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

for router in (
    health.router,
    agents.router,
    commands.router,
    sessions.router,
    session_tasks.router,
    session_governance.router,
    plan_execute.router,
    room.router,
):
    app.include_router(router)

_WEB_DIST = _ROOT / "web" / "dist"
if _WEB_DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(_WEB_DIST), html=True), name="web")
