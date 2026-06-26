"""Kimi Work daimon Control WS peer bridge (cursor_bridge pattern).

P0: in-process mock RPC when AGENT_LAB_MOCK_AGENTS=1.
P1: headless daimon spawn (or Kimi.app attach) + websockets RPC.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

KIMI_WORK_BRIDGE_FALLBACK = (
    "Kimi Work 제외 후 KIMI API / Local 로 대체하거나 Kimi 앱·daimon 재연결 후 재시도"
)
KIMI_WORK_BRIDGE_REMEDIATION = (
    "Kimi 앱에서 Work 최초 로그인(또는 토큰 만료 시 재로그인)",
    "상태 패널에서 Kimi Work bridge 재연결",
    "KIMI_SHARE_DIR / daimon-share config.json 경로 확인",
)

_BRIDGE_RETRY_ATTEMPTS = 3
_BRIDGE_RETRY_BACKOFF_S = 0.35
_WS_RESOLVE_ATTEMPTS = 2
_WS_RPC_TIMEOUT_S = 120.0
_PUSH_METHODS = frozenset(
    {
        "conversations.message.snapshot",
        "conversations.message.complete",
        "conversations.message.error",
        "conversations.message.cancelled",
    }
)


class KimiWorkBridgeUnavailable(RuntimeError):
    """Structured bridge failure for health, preflight, and agent-turn fallback."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "kimi_work_bridge_unavailable",
        fallback: str = KIMI_WORK_BRIDGE_FALLBACK,
        remediation: tuple[str, ...] = KIMI_WORK_BRIDGE_REMEDIATION,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.fallback = fallback
        self.remediation = remediation


@dataclass(frozen=True)
class ControlEndpoint:
    url: str
    token: str
    auth_mode: str = "loopback-dev-token"


_endpoint_cache: ControlEndpoint | None = None
_cache_lock = threading.Lock()
_rpc_lock = threading.Lock()
_async_loop_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kimi-ws-rpc")


def _mock_enabled() -> bool:
    return os.getenv("AGENT_LAB_MOCK_AGENTS", "").strip().lower() in {"1", "true", "yes", "on"}


def default_share_dir() -> Path:
    raw = (os.getenv("KIMI_SHARE_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/kimi-desktop/daimon-share"
    return Path.home() / ".kimi"


def daimon_config_path() -> Path:
    return default_share_dir() / "daimon" / "config.json"


def is_share_configured() -> bool:
    """True when Kimi Work peer credentials layout exists (no secret reads)."""
    return daimon_config_path().is_file()


def is_transient_bridge_error(exc: BaseException) -> bool:
    if isinstance(exc, KimiWorkBridgeUnavailable):
        text = str(exc).lower()
        return "connection refused" in text or "timed out" in text or "temporarily unavailable" in text
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "connection refused",
            "errno 61",
            "timed out",
            "timeout",
            "temporarily unavailable",
            "connecterror",
        )
    )


def kimi_work_bridge_failure_payload(
    exc: BaseException | None = None,
    *,
    reason: str | None = None,
) -> dict[str, object]:
    if isinstance(exc, KimiWorkBridgeUnavailable):
        msg = str(exc).strip()
        return {
            "degraded": True,
            "failure_code": exc.code,
            "reason": msg,
            "fallback": exc.fallback,
            "remediation": list(exc.remediation),
        }
    msg = reason or (str(exc).strip() if exc else "") or "Kimi Work bridge 연결 실패"
    return {
        "degraded": True,
        "failure_code": "kimi_work_bridge_unavailable",
        "reason": msg,
        "fallback": KIMI_WORK_BRIDGE_FALLBACK,
        "remediation": list(KIMI_WORK_BRIDGE_REMEDIATION),
    }


def invalidate_endpoint_cache() -> None:
    global _endpoint_cache
    with _cache_lock:
        _endpoint_cache = None


def _refresh_bridge_on_probe_failure() -> None:
    invalidate_endpoint_cache()
    from agent_lab.kimi_daimon_supervisor import is_owned_pid, read_lock_owner_pid, shutdown_owned_daimon

    lock_pid = read_lock_owner_pid()
    if lock_pid is not None and is_owned_pid(lock_pid):
        shutdown_owned_daimon()


def probe_endpoint_ws(endpoint: ControlEndpoint) -> bool:
    """Lightweight WS capabilities probe (public for supervisor attach path)."""
    return _probe_endpoint_ws(endpoint)


def _resolve_live_endpoint() -> ControlEndpoint:
    """Ensure daimon endpoint (attach or spawn) with WS verified inside supervisor."""
    from agent_lab.backoff_policy import wait as backoff_wait
    from agent_lab.kimi_daimon_supervisor import ensure_daimon

    last_exc: KimiWorkBridgeUnavailable | None = None
    for attempt in range(_WS_RESOLVE_ATTEMPTS):
        try:
            return ensure_daimon()
        except KimiWorkBridgeUnavailable as exc:
            last_exc = exc
            invalidate_endpoint_cache()
            _refresh_bridge_on_probe_failure()
            if attempt + 1 < _WS_RESOLVE_ATTEMPTS:
                backoff_wait(attempt + 1, base_sec=0.75)
    raise KimiWorkBridgeUnavailable(
        "daimon Control WS에 연결할 수 없습니다 — Kimi 앱을 완전히 종료한 뒤 bridge 재연결 또는 make dev 재시작",
        code="kimi_work_bridge_unavailable",
    ) from last_exc


def discover_endpoint() -> ControlEndpoint | None:
    """Resolve control endpoint — Kimi.app attach when running, else headless spawn."""
    if _mock_enabled():
        return ControlEndpoint(url="ws://127.0.0.1:0/control", token="mock-token")
    try:
        return _resolve_live_endpoint()
    except KimiWorkBridgeUnavailable:
        return None


def _probe_endpoint_ws(endpoint: ControlEndpoint) -> bool:
    try:
        result = _live_rpc(endpoint, "capabilities.get", {}, on_push=None, timeout_s=8.0)
    except Exception:
        return False
    if not isinstance(result, dict):
        return False
    features = result.get("features")
    if not isinstance(features, list):
        return False
    return "conversations.send" in features


def probe_control() -> tuple[str, str | None]:
    """Return (bridge_status, error_hint) for health rows."""
    if _mock_enabled():
        return "ok", None
    if not is_share_configured():
        return "error", "Kimi Work daimon-share config 없음 — Kimi 앱에서 Work 최초 로그인"
    try:
        endpoint = _resolve_live_endpoint()
    except KimiWorkBridgeUnavailable as exc:
        return "error", str(exc)
    global _endpoint_cache
    with _cache_lock:
        _endpoint_cache = endpoint
    return "ok", None


def _get_endpoint() -> ControlEndpoint:
    global _endpoint_cache
    with _cache_lock:
        if _endpoint_cache is not None:
            return _endpoint_cache
    try:
        endpoint = _resolve_live_endpoint()
    except KimiWorkBridgeUnavailable:
        raise
    with _cache_lock:
        if _endpoint_cache is None:
            _endpoint_cache = endpoint
        return _endpoint_cache


def _mock_capabilities_get() -> dict[str, Any]:
    features = [
        "capabilities.get",
        "conversations.create",
        "conversations.send",
        "conversations.submitToolResult",
        "workspace.openProject",
        "workspace.addEntry",
        "inbox.askHuman",
        "inbox.proposeBuild",
    ]
    return {"features": features}


def _mock_open_project(path: str) -> dict[str, Any]:
    return {"status": "opened", "project": {"path": path}}


def _mock_add_entry(path: str) -> dict[str, Any]:
    return {"status": "added", "entry": {"path": path}}


def _mock_conversations_create(*, title: str | None = None) -> str:
    safe = (title or "agent-lab").replace(" ", "-")[:32]
    return f"mock-conv-{safe}"


def _mock_send_turn(
    *,
    conversation_key: str,
    text: str,
    system: str | None,
    on_push: Callable[[str, dict[str, Any]], None] | None,
) -> str:
    final_holder: list[str] = []

    def _emit(method: str, payload: dict[str, Any]) -> None:
        if method == "conversations.message.complete":
            from agent_lab.kimi_work_push_payload import assistant_reply_text

            body = assistant_reply_text(payload) or str(payload.get("text") or "").strip()
            if body:
                final_holder.append(body)
        if on_push is not None:
            on_push(method, payload)

    if "[mock-tools]" in text:
        _emit(
            "conversations.message.snapshot",
            {
                "conversationKey": conversation_key,
                "parts": [
                    {
                        "kind": "tool-call",
                        "toolCallId": "mock-tc-1",
                        "toolName": "read_file",
                        "args": '{"path":"README.md"}',
                    },
                ],
            },
        )
        _emit(
            "conversations.message.snapshot",
            {
                "conversationKey": conversation_key,
                "parts": [
                    {
                        "kind": "tool-call",
                        "toolCallId": "mock-tc-1",
                        "toolName": "read_file",
                        "args": '{"path":"README.md"}',
                    },
                    {
                        "kind": "tool-result",
                        "toolCallId": "mock-tc-1",
                        "result": "# mock file\n",
                    },
                ],
            },
        )
        body = "Tool turn complete."
        _emit("conversations.message.snapshot", {"conversationKey": conversation_key, "text": body})
        _emit("conversations.message.complete", {"conversationKey": conversation_key, "text": body})
        return body

    if "[mock-inbox-ask]" in text:
        call_id = "mock-inbox-ask-1"
        _emit(
            "conversations.message.snapshot",
            {
                "conversationKey": conversation_key,
                "parts": [
                    {
                        "kind": "tool-call",
                        "toolCallId": call_id,
                        "toolName": "ask_human",
                        "args": json.dumps(
                            {
                                "question": "Which scope for this Loop step?",
                                "options": [
                                    {"id": "narrow", "label": "Minimal change"},
                                    {"id": "broad", "label": "Broader refactor"},
                                ],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
            },
        )
        return final_holder[-1] if final_holder else ""

    snippet = " ".join((text or "").strip().split())[:100]
    body = f"[mock:Kimi Work] ACK — {snippet or '(empty)'}"
    if system and ("Structured envelope" in system or "Loop consensus envelope" in system):
        body = '{"act":"ENDORSE","refs":[],"confidence":0.9}\n' + body
    if system and system.strip():
        body = f"{body}\n(system: {system.strip()[:60]}…)" if len(system.strip()) > 60 else f"{body}\n(system: {system.strip()})"
    if on_push:
        from agent_lab.room_sse_stream import chunk_text

        acc = ""
        for chunk in chunk_text(body, chunk_size=16):
            acc += chunk
            _emit("conversations.message.snapshot", {"conversationKey": conversation_key, "text": acc})
        _emit("conversations.message.complete", {"conversationKey": conversation_key, "text": body})
    return body


def _mock_submit_tool_result(
    *,
    conversation_key: str,
    tool_call_id: str,
    result: dict[str, Any],
    on_push: Callable[[str, dict[str, Any]], None] | None,
) -> dict[str, Any]:
    payload_text = json.dumps(result, ensure_ascii=False)
    if on_push:
        on_push(
            "conversations.message.snapshot",
            {
                "conversationKey": conversation_key,
                "parts": [
                    {
                        "kind": "tool-result",
                        "toolCallId": tool_call_id,
                        "result": payload_text,
                    },
                ],
            },
        )
        summary = result.get("selected") or result.get("decision") or result.get("status") or "ok"
        body = f"Inbox resolved ({summary})."
        on_push(
            "conversations.message.snapshot",
            {"conversationKey": conversation_key, "text": body},
        )
        on_push(
            "conversations.message.complete",
            {"conversationKey": conversation_key, "text": body},
        )
    return {"status": "submitted", "toolCallId": tool_call_id}


def _daimon_submit_tool_result_supported() -> bool:
    if _mock_enabled():
        return True
    try:
        caps = rpc("capabilities.get", {})
        features = caps.get("features") if isinstance(caps, dict) else None
        if isinstance(features, list):
            normalized = {str(item).strip() for item in features if str(item).strip()}
            return "conversations.submitToolResult" in normalized
    except Exception:
        pass
    return False


def submit_conversation_tool_result(
    *,
    conversation_key: str,
    tool_call_id: str,
    result: dict[str, Any],
    on_push: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Return inbox tool result to daimon so the Kimi Work turn can continue."""
    params = {
        "conversationKey": conversation_key,
        "toolCallId": tool_call_id,
        "result": result,
    }
    if _mock_enabled():
        return _mock_submit_tool_result(
            conversation_key=conversation_key,
            tool_call_id=tool_call_id,
            result=result,
            on_push=on_push,
        )
    if not _daimon_submit_tool_result_supported():
        follow_up = (
            f"[tool_result {tool_call_id}]\n{json.dumps(result, ensure_ascii=False)}\n"
            "Continue using this Human Inbox result."
        )
        send_turn(
            conversation_key=conversation_key,
            text=follow_up,
            system=None,
            on_push=on_push,
        )
        return {"status": "fallback_send", "toolCallId": tool_call_id}
    return rpc("conversations.submitToolResult", params, on_push=on_push)


from agent_lab.kimi_work_push_payload import assistant_reply_text, push_message_parts


async def _ws_rpc_loop(
    endpoint: ControlEndpoint,
    method: str,
    params: dict[str, Any],
    *,
    on_push: Callable[[str, dict[str, Any]], None] | None,
    timeout_s: float,
    wait_for_complete: bool,
) -> Any:
    import websockets

    headers = {"Authorization": f"Bearer {endpoint.token}"}
    final_text = ""
    from agent_lab.room_sse_stream import CumulativeTextStreamer

    text_stream = CumulativeTextStreamer()
    req_id = 1
    async with websockets.connect(endpoint.url, additional_headers=headers) as ws:
        await ws.send(
            json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}),
        )
        result: Any = None
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout_s)
            msg = json.loads(raw)
            push_method = msg.get("method")
            if isinstance(push_method, str) and push_method in _PUSH_METHODS:
                payload = msg.get("params")
                payload_dict = payload if isinstance(payload, dict) else {}
                if on_push is not None:
                    on_push(push_method, payload_dict)
                if push_method == "conversations.message.snapshot":
                    snap_text = assistant_reply_text(payload_dict)
                    if snap_text:
                        text_stream.feed(snap_text)
                    continue
                if push_method == "conversations.message.error":
                    err_text = str(payload_dict.get("message") or payload_dict.get("error") or "message error")
                    raise KimiWorkBridgeUnavailable(err_text, code="kimi_work_message_error")
                if push_method == "conversations.message.complete":
                    final_text = assistant_reply_text(payload_dict) or text_stream.body
                    if wait_for_complete and method == "conversations.send":
                        return final_text
                continue
            if msg.get("id") == req_id:
                if msg.get("error"):
                    err = msg["error"]
                    if isinstance(err, dict):
                        raise KimiWorkBridgeUnavailable(str(err.get("message") or err))
                    raise KimiWorkBridgeUnavailable(str(err))
                result = msg.get("result")
                if method == "conversations.send" and wait_for_complete:
                    continue
                return result
    return result


def _live_rpc(
    endpoint: ControlEndpoint,
    method: str,
    params: dict[str, Any] | None,
    *,
    on_push: Callable[[str, dict[str, Any]], None] | None,
    timeout_s: float = _WS_RPC_TIMEOUT_S,
) -> Any:
    wait_for_complete = method == "conversations.send"

    def _run_in_fresh_loop() -> Any:
        return asyncio.run(
            _ws_rpc_loop(
                endpoint,
                method,
                params or {},
                on_push=on_push,
                timeout_s=timeout_s,
                wait_for_complete=wait_for_complete,
            ),
        )

    with _rpc_lock:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return _run_in_fresh_loop()
        # FastAPI async handlers already have a running loop — run WS RPC in a side thread.
        return _async_loop_executor.submit(_run_in_fresh_loop).result()


def rpc(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    on_push: Callable[[str, dict[str, Any]], None] | None = None,
) -> Any:
    """Dispatch a control RPC (mock or live WS)."""
    if _mock_enabled():
        params = params or {}
        if method == "capabilities.get":
            return _mock_capabilities_get()
        if method == "conversations.create":
            return {"conversationKey": _mock_conversations_create(title=str(params.get("title") or ""))}
        if method == "conversations.send":
            return _mock_send_turn(
                conversation_key=str(params.get("conversationKey") or ""),
                text=str(params.get("text") or ""),
                system=str(params.get("system") or "") or None,
                on_push=on_push,
            )
        if method == "conversations.submitToolResult":
            raw_result = params.get("result")
            if not isinstance(raw_result, dict):
                raw_result = {}
            return _mock_submit_tool_result(
                conversation_key=str(params.get("conversationKey") or ""),
                tool_call_id=str(params.get("toolCallId") or ""),
                result=raw_result,
                on_push=on_push,
            )
        if method == "workspace.openProject":
            path = str(params.get("path") or "")
            if path.endswith("/openProject-fail"):
                raise KimiWorkBridgeUnavailable("mock openProject failure")
            return _mock_open_project(path)
        if method == "workspace.addEntry":
            return _mock_add_entry(str(params.get("path") or ""))
        raise KimiWorkBridgeUnavailable(f"unsupported mock RPC method: {method}")

    endpoint = _get_endpoint()
    try:
        return _live_rpc(endpoint, method, params or {}, on_push=on_push)
    except Exception as exc:
        if not is_transient_bridge_error(exc):
            raise
        invalidate_endpoint_cache()
        _refresh_bridge_on_probe_failure()
        endpoint = _get_endpoint()
        return _live_rpc(endpoint, method, params or {}, on_push=on_push)


def send_turn(
    *,
    conversation_key: str,
    text: str,
    system: str | None = None,
    on_push: Callable[[str, dict[str, Any]], None] | None = None,
) -> str:
    """Send one Room turn via conversations.send (+ mock push snapshots)."""
    last_err: BaseException | None = None
    for attempt in range(_BRIDGE_RETRY_ATTEMPTS):
        try:
            result = rpc(
                "conversations.send",
                {"conversationKey": conversation_key, "text": text, "system": system or ""},
                on_push=on_push,
            )
            if isinstance(result, str):
                return result
            return str(result)
        except KimiWorkBridgeUnavailable:
            invalidate_endpoint_cache()
            raise
        except Exception as exc:
            last_err = exc
            if is_transient_bridge_error(exc) and attempt + 1 < _BRIDGE_RETRY_ATTEMPTS:
                invalidate_endpoint_cache()
                from agent_lab.kimi_daimon_supervisor import shutdown_owned_daimon

                shutdown_owned_daimon()
                from agent_lab.backoff_policy import wait as _backoff_wait

                _backoff_wait(attempt + 1, base_sec=_BRIDGE_RETRY_BACKOFF_S)
                continue
            raise KimiWorkBridgeUnavailable(str(exc)) from exc
    raise KimiWorkBridgeUnavailable(str(last_err or "Kimi Work bridge failed"))
