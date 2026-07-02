"""Agent Lab API — FastAPI backend for the web UI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_lab.app_logging import setup_app_logging
from app.server.bootstrap import bootstrap_environment, project_root

_ROOT = project_root()


def _api_startup() -> None:
    from agent_lab.agent.auth_bootstrap import bootstrap_room_auth_on_startup
    from agent_lab.app_logging import write_boot_line
    from agent_lab.daemon_state import mark_daemon_started
    from agent_lab.mission.scheduler import start_mission_scheduler_background

    try:
        from agent_lab.run.profile import apply_run_profile, default_run_profile

        applied = apply_run_profile(default_run_profile())
        if applied:
            write_boot_line(f"run profile applied flags: {list(applied.keys())}")
    except Exception as exc:
        write_boot_line(f"run profile apply failed: {exc}")
    try:
        bootstrap_room_auth_on_startup()
    except Exception as exc:
        write_boot_line(f"auth bootstrap failed: {exc}")
    try:
        from agent_lab.room.models_config import apply_default_room_models_to_env

        apply_default_room_models_to_env()
    except Exception as exc:
        write_boot_line(f"default room models apply failed: {exc}")
    try:
        from agent_lab.run.control import maybe_release_orphaned_run_lock

        if maybe_release_orphaned_run_lock():
            write_boot_line("startup: released orphaned run lock")
    except Exception as exc:
        write_boot_line(f"startup: run lock cleanup failed: {exc}")
    try:
        from agent_lab.api_diagnostics import build_diagnostics_payload

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
        from agent_lab.kimi.control_client import warm_bridge

        warm_bridge(background=True)
        from agent_lab.agent.catalog_runtime import warm_catalog_on_startup

        warm_catalog_on_startup(background=True)
    except Exception as exc:
        write_boot_line(f"uvicorn startup diagnostics failed: {exc}")


def _api_shutdown() -> None:
    from agent_lab.background_tasks import get_manager
    from agent_lab.kimi.daimon_supervisor import _keep_daimon_on_api_shutdown, detach_owned_daimon, shutdown_owned_daimon

    try:
        get_manager().shutdown()
    except Exception:
        pass

    if _keep_daimon_on_api_shutdown():
        detach_owned_daimon()
    else:
        shutdown_owned_daimon()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    bootstrap_environment(root=_ROOT)
    _api_startup()
    yield
    _api_shutdown()


def create_app(*, bootstrap: bool = False) -> FastAPI:
    """Factory for the FastAPI app. Pass bootstrap=True to apply env before serving."""
    if bootstrap:
        bootstrap_environment(root=_ROOT)

    setup_app_logging()

    from app.server.routers import (
        agents,
        auth,
        background_tasks,
        commands,
        context_layers,
        dev_preview,
        eval_memory,
        evidence_api,
        gateway,
        health,
        human_inbox,
        mission_loop,
        mission_os,
        openai_compat,
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
    from app.server.exceptions import register_exception_handlers

    application = FastAPI(title="Agent Lab API", version="0.1.0", lifespan=lifespan)
    application.add_middleware(
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

    register_exception_handlers(application)

    for router in (
        health.router,
        auth.router,
        agents.router,
        background_tasks.router,
        commands.router,
        context_layers.router,
        dev_preview.router,
        eval_memory.router,
        evidence_api.router,
        gateway.router,
        sessions.router,
        session_tasks.router,
        session_governance.router,
        human_inbox.router,
        mission_loop.router,
        mission_os.router,
        openai_compat.router,
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
        application.include_router(router)

    web_dist = _ROOT / "web" / "dist"
    if web_dist.is_dir():
        from fastapi.staticfiles import StaticFiles

        application.mount("/", StaticFiles(directory=str(web_dist), html=True), name="web")

    return application


app = create_app()
