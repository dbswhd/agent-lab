"""WebSocket-based PTY terminal endpoint (Phase 4)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agent_lab import terminal as term
from agent_lab.run_meta import read_run_meta
from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")


def _workspace_cwd(folder: Path) -> Path:
    """Return the workspace root for this session's terminal cwd."""
    meta = read_run_meta(folder)
    binding = meta.get("workspace_binding") or {}
    path_str = binding.get("path")
    if path_str:
        p = Path(path_str)
        if p.is_dir():
            return p
    return folder


@router.websocket("/sessions/{session_id}/terminal")
async def terminal_ws(ws: WebSocket, session_id: str) -> None:
    folder = session_folder_or_404(session_id)
    cwd = _workspace_cwd(folder)

    await ws.accept()

    sess = term.spawn(session_id, cwd)

    async def _read_loop() -> None:
        while True:
            chunk = await term.read_output(sess.fd)
            if chunk is None:  # EOF / process exited
                try:
                    await ws.send_json({"type": "exit"})
                except Exception:
                    pass
                return
            if chunk:
                try:
                    await ws.send_json(
                        {
                            "type": "output",
                            "data": chunk.decode("utf-8", errors="replace"),
                        }
                    )
                except Exception:
                    return

    async def _write_loop() -> None:
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send a keepalive ping.
                try:
                    await ws.send_json({"type": "ping"})
                except Exception:
                    return
                continue
            except WebSocketDisconnect:
                return
            msg_type = msg.get("type")
            if msg_type == "input":
                try:
                    term.write_input(sess.fd, msg["data"].encode())
                except OSError:
                    return
            elif msg_type == "resize":
                try:
                    term.resize(
                        sess.fd,
                        int(msg.get("rows", 24)),
                        int(msg.get("cols", 80)),
                    )
                except OSError:
                    return

    try:
        await asyncio.gather(_read_loop(), _write_loop())
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        term.close_session(session_id)
