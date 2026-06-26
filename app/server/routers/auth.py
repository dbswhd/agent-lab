from __future__ import annotations

from typing import Literal

import anyio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from agent_lab.auth_runs import (
    cancel_auth_run,
    capture_codex_run,
    drain_auth_events,
    get_auth_run,
    provider_status_payload,
    send_auth_input,
)

router = APIRouter(prefix="/api")


class CodexCaptureRequest(BaseModel):
    slot: Literal["primary", "fallback"]
    confirm: bool = False


@router.get("/auth/providers")
def get_auth_providers() -> dict[str, object]:
    return provider_status_payload()


@router.post("/auth/runs/{run_id}/codex-capture")
def post_codex_capture(run_id: str, body: CodexCaptureRequest) -> dict[str, object]:
    try:
        capture = capture_codex_run(run_id, body.slot, confirm=body.confirm)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "capture": capture}


@router.websocket("/auth/runs/{run_id}")
async def auth_run_ws(ws: WebSocket, run_id: str) -> None:
    run = get_auth_run(run_id)
    await ws.accept()
    if run is None:
        await ws.send_json({"type": "failed", "detail": "auth run not found"})
        await ws.close(code=4404)
        return
    try:
        while True:
            for event in drain_auth_events(run):
                await ws.send_json(event)
            if run.status != "running":
                await ws.close(code=1000)
                return
            with anyio.move_on_after(0.08) as scope:
                message = await ws.receive_json()
            if scope.cancel_called:
                continue
            if message.get("type") == "input":
                send_auth_input(run, str(message.get("data") or ""))
            elif message.get("type") == "cancel":
                cancel_auth_run(run)
    except WebSocketDisconnect:
        return
