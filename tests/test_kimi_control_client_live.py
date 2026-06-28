"""Live-style Kimi Control WS client tests (in-process fake server, no real daimon)."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any

import pytest

from agent_lab.kimi.control_client import (
    ControlEndpoint,
    _live_rpc,
    discover_endpoint,
    invalidate_endpoint_cache,
    mark_probe_ok,
    probe_control,
    rpc_batch,
    send_turn,
)


async def _fake_ws_handler(websocket: Any) -> None:
    async for raw in websocket:
        msg = json.loads(raw)
        method = msg.get("method")
        req_id = msg.get("id")
        if method == "capabilities.get":
            await websocket.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"features": ["capabilities.get", "conversations.send", "conversations.create"]},
                    },
                ),
            )
        elif method == "conversations.send":
            text = str((msg.get("params") or {}).get("text") or "")
            body = f"live:{text}"
            await websocket.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "conversations.message.snapshot",
                        "params": {"text": body[:4]},
                    },
                ),
            )
            await websocket.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "conversations.message.complete",
                        "params": {"text": body},
                    },
                ),
            )
            await websocket.send(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"ok": True}}))
        elif method == "workspace.openProject":
            path = str((msg.get("params") or {}).get("path") or "")
            await websocket.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"status": "opened", "project": {"path": path}},
                    },
                ),
            )
        elif method == "conversations.create":
            await websocket.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"conversationKey": "main:conversation:batch-test"},
                    },
                ),
            )
        else:
            await websocket.send(
                json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"message": f"unsupported {method}"}}),
            )


@pytest.fixture
def fake_ws_server() -> ControlEndpoint:
    pytest.importorskip("websockets")
    import websockets

    ready = threading.Event()
    holder: dict[str, Any] = {}

    def _run() -> None:
        async def _serve() -> None:
            async with websockets.serve(_fake_ws_handler, "127.0.0.1", 0) as server:
                port = server.sockets[0].getsockname()[1]
                holder["endpoint"] = ControlEndpoint(
                    url=f"ws://127.0.0.1:{port}/control",
                    token="fake-token",
                )
                ready.set()
                await asyncio.Future()

        asyncio.run(_serve())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    assert ready.wait(timeout=5)
    return holder["endpoint"]


def test_live_rpc_send_turn(fake_ws_server: ControlEndpoint) -> None:
    chunks: list[str] = []

    def on_push(method: str, payload: dict) -> None:
        if method == "conversations.message.snapshot":
            chunks.append(str(payload.get("text") or ""))

    text = _live_rpc(
        fake_ws_server,
        "conversations.send",
        {"conversationKey": "c1", "text": "hello"},
        on_push=on_push,
        timeout_s=5.0,
    )
    assert text == "live:hello"
    assert chunks


def test_discover_endpoint_with_mocked_supervisor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_ws_server: ControlEndpoint,
) -> None:
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    monkeypatch.setenv("KIMI_SHARE_DIR", str(tmp_path / "share"))
    share = tmp_path / "share"
    (share / "daimon").mkdir(parents=True)
    (share / "daimon" / "config.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        "agent_lab.kimi.daimon_supervisor.ensure_daimon",
        lambda: fake_ws_server,
    )
    invalidate_endpoint_cache()
    ep = discover_endpoint()
    assert ep is not None
    assert ep.url == fake_ws_server.url


def test_probe_control_ok(monkeypatch: pytest.MonkeyPatch, fake_ws_server: ControlEndpoint) -> None:
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    monkeypatch.setattr(
        "agent_lab.kimi.daimon_supervisor.ensure_daimon",
        lambda: fake_ws_server,
    )
    share = Path("/tmp/unused")
    monkeypatch.setattr("agent_lab.kimi.control_client.is_share_configured", lambda: True)
    bridge, err = probe_control()
    assert bridge == "ok"
    assert err is None


def test_send_turn_live_path(monkeypatch: pytest.MonkeyPatch, fake_ws_server: ControlEndpoint) -> None:
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    monkeypatch.setattr(
        "agent_lab.kimi.daimon_supervisor.ensure_daimon",
        lambda: fake_ws_server,
    )
    invalidate_endpoint_cache()
    monkeypatch.setattr(
        "agent_lab.kimi.control_client._get_endpoint",
        lambda: fake_ws_server,
    )
    out = send_turn(conversation_key="c1", text="ping")
    assert out == "live:ping"


async def _fake_ws_handler_complete_without_text(websocket: Any) -> None:
    async for raw in websocket:
        msg = json.loads(raw)
        method = msg.get("method")
        req_id = msg.get("id")
        if method == "conversations.send":
            await websocket.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "conversations.message.snapshot",
                        "params": {"text": "snap-only body"},
                    },
                ),
            )
            await websocket.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "conversations.message.complete",
                        "params": {},
                    },
                ),
            )
            await websocket.send(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"ok": True}}))
        else:
            await websocket.send(
                json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"ok": True}}),
            )


@pytest.fixture
def fake_ws_server_snapshot_body() -> ControlEndpoint:
    pytest.importorskip("websockets")
    import websockets

    ready = threading.Event()
    holder: dict[str, Any] = {}

    def _run() -> None:
        async def _serve() -> None:
            async with websockets.serve(_fake_ws_handler_complete_without_text, "127.0.0.1", 0) as server:
                port = server.sockets[0].getsockname()[1]
                holder["endpoint"] = ControlEndpoint(
                    url=f"ws://127.0.0.1:{port}/control",
                    token="fake-token",
                )
                ready.set()
                await asyncio.Future()

        asyncio.run(_serve())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    assert ready.wait(timeout=5)
    return holder["endpoint"]


def test_send_turn_uses_snapshot_when_complete_text_empty(
    monkeypatch: pytest.MonkeyPatch,
    fake_ws_server_snapshot_body: ControlEndpoint,
) -> None:
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    monkeypatch.setattr(
        "agent_lab.kimi.control_client._get_endpoint",
        lambda: fake_ws_server_snapshot_body,
    )
    out = send_turn(conversation_key="main:conversation:abc", text="ping")
    assert out == "snap-only body"


def test_get_endpoint_reuses_warm_cache(
    monkeypatch: pytest.MonkeyPatch,
    fake_ws_server: ControlEndpoint,
) -> None:
    from agent_lab.kimi.control_client import _get_endpoint, invalidate_endpoint_cache

    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    calls = {"n": 0}

    def _resolve() -> ControlEndpoint:
        calls["n"] += 1
        return fake_ws_server

    invalidate_endpoint_cache()
    monkeypatch.setattr("agent_lab.kimi.control_client._resolve_live_endpoint", _resolve)
    ep1 = _get_endpoint()
    ep2 = _get_endpoint()
    assert ep1.url == fake_ws_server.url
    assert ep2.url == fake_ws_server.url
    assert calls["n"] == 1


def test_live_rpc_works_under_running_event_loop(fake_ws_server: ControlEndpoint) -> None:
    from agent_lab.kimi.control_client import _live_rpc

    async def _call_under_loop() -> dict[str, Any]:
        result = _live_rpc(fake_ws_server, "capabilities.get", {}, on_push=None, timeout_s=5.0)
        assert isinstance(result, dict)
        return result

    payload = asyncio.run(_call_under_loop())
    assert "conversations.send" in payload.get("features", [])


def test_probe_control_skips_resolve_when_recent(
    monkeypatch: pytest.MonkeyPatch,
    fake_ws_server: ControlEndpoint,
) -> None:
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    calls = {"n": 0}

    def _resolve() -> ControlEndpoint:
        calls["n"] += 1
        return fake_ws_server

    invalidate_endpoint_cache()
    monkeypatch.setattr("agent_lab.kimi.control_client.is_share_configured", lambda: True)
    monkeypatch.setattr("agent_lab.kimi.control_client._resolve_live_endpoint", _resolve)
    bridge, err = probe_control()
    assert bridge == "ok"
    assert err is None
    assert calls["n"] == 1
    bridge2, err2 = probe_control()
    assert bridge2 == "ok"
    assert err2 is None
    assert calls["n"] == 1


def test_rpc_batch_single_ws(
    monkeypatch: pytest.MonkeyPatch,
    fake_ws_server: ControlEndpoint,
) -> None:
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    invalidate_endpoint_cache()
    monkeypatch.setattr(
        "agent_lab.kimi.control_client._get_endpoint",
        lambda: fake_ws_server,
    )
    results = rpc_batch(
        [
            ("workspace.openProject", {"path": "/tmp/proj"}),
            ("conversations.create", {"sessionKey": "main", "title": "t"}),
        ],
    )
    assert results[0]["project"]["path"] == "/tmp/proj"
    assert results[1]["conversationKey"] == "main:conversation:batch-test"


def test_send_turn_retries_after_transient_error(monkeypatch: pytest.MonkeyPatch, fake_ws_server: ControlEndpoint) -> None:
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    calls = {"n": 0}
    shutdowns: list[str] = []

    def _live_rpc(_endpoint, _method, _params, *, on_push, timeout_s=120.0):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("connection refused")
        return "live:retry"

    monkeypatch.setattr("agent_lab.kimi.control_client._live_rpc", _live_rpc)
    monkeypatch.setattr("agent_lab.kimi.control_client._get_endpoint", lambda: fake_ws_server)

    def _refresh() -> None:
        shutdowns.append("yes")

    monkeypatch.setattr("agent_lab.kimi.control_client._refresh_bridge_on_probe_failure", _refresh)
    invalidate_endpoint_cache()
    out = send_turn(conversation_key="c1", text="retry")
    assert out == "live:retry"
    assert calls["n"] == 2
    assert shutdowns == ["yes"]

