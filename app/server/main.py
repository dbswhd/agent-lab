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

from agent_lab.credential_store import apply_credentials_to_env  # noqa: E402

apply_credentials_to_env()

from agent_lab.api_diagnostics import build_diagnostics_payload  # noqa: E402
from app.server.routers import (  # noqa: E402
    agents,
    auth,
    background_tasks,
    commands,
    context_layers,
    dev_preview,
    gateway,
    health,
    human_inbox,
    mission_loop,
    mission_os,
    plan_execute,
    plan_workflow,
    room,
    runtime,
    session_governance,
    session_tasks,
    sessions,
    settings,
    skill_drafts,
    terminal,
    verified_loop,
    workspace_files,
)

setup_app_logging()


def _api_startup() -> None:
    from agent_lab.agent_auth_bootstrap import bootstrap_room_auth_on_startup
    from agent_lab.app_logging import write_boot_line
    from agent_lab.daemon_state import mark_daemon_started
    from agent_lab.mission_scheduler import start_mission_scheduler_background

    try:
        bootstrap_room_auth_on_startup()
    except Exception as exc:
        write_boot_line(f"auth bootstrap failed: {exc}")
    try:
        from agent_lab.room_models_config import apply_default_room_models_to_env

        apply_default_room_models_to_env()
    except Exception as exc:
        write_boot_line(f"default room models apply failed: {exc}")
    try:
        payload = build_diagnostics_payload()
        write_boot_line(
            "uvicorn startup pid=%s port=%s sessions=%s" % (payload["pid"], payload["port"], payload["sessions_dir"])
        )
        mark_daemon_started(pid=int(payload["pid"]))
        from agent_lab.crash_recovery import crash_recovery_enabled, reconcile_crashed_merges

        if crash_recovery_enabled():
            from agent_lab.daemon_state import record_last_recovery

            rec = reconcile_crashed_merges()
            write_boot_line(
                "crash-recovery scanned=%s merged=%s rolled_back=%s quarantined=%s errors=%s"
                % (
                    rec["scanned"],
                    rec["reconciled_merged"],
                    rec["rolled_back"],
                    rec["quarantined"],
                    rec["errors"],
                )
            )
            record_last_recovery(rec)
        if start_mission_scheduler_background():
            write_boot_line("mission scheduler background thread started")
    except Exception as exc:
        write_boot_line(f"uvicorn startup diagnostics failed: {exc}")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _api_startup()
    yield
    from agent_lab.kimi_daimon_supervisor import shutdown_owned_daimon

    shutdown_owned_daimon()


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
    auth.router,
    agents.router,
    background_tasks.router,
    commands.router,
    context_layers.router,
    dev_preview.router,
    gateway.router,
    sessions.router,
    session_tasks.router,
    session_governance.router,
    human_inbox.router,
    mission_loop.router,
    mission_os.router,
    plan_execute.router,
    plan_workflow.router,
    skill_drafts.router,
    runtime.router,
    room.router,
    settings.router,
    terminal.router,
    verified_loop.router,
    workspace_files.router,
):
    app.include_router(router)

_WEB_DIST = _ROOT / "web" / "dist"
if _WEB_DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(_WEB_DIST), html=True), name="web")
