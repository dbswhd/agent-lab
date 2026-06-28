"""Workspace-scoped Cursor SDK bridge lifecycle (avoids stale global bridge / cwd mismatch)."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

CURSOR_BRIDGE_FALLBACK = "Cursor 제외 후 Codex/Claude 로컬 CLI로 전송하거나 Cursor bridge 재연결 후 재시도"
CURSOR_BRIDGE_REMEDIATION = (
    "Cursor 앱 실행",
    "상태 패널의 재연결 버튼으로 bridge ping 재시도",
    "CURSOR_SDK_BRIDGE_URL 이 죽은 IDE bridge 를 가리키면 unset",
    "GUI 앱에서는 ~/.agent-lab/.env 의 CURSOR_SDK_BRIDGE_BIN 절대경로 확인",
)
_BRIDGE_HINT = (
    "Cursor bridge 연결 실패. 확인: (1) CURSOR_API_KEY 설정 "
    "(2) pip install -e '.[cursor]' "
    "(3) CURSOR_SDK_BRIDGE_URL 이 죽은 IDE bridge 를 가리키면 unset "
    "(4) GUI 앱: ~/.agent-lab/.env 에 CURSOR_SDK_BRIDGE_BIN 절대경로 "
    "(5) Cursor 앱 실행 후 재시도"
)


class CursorBridgeUnavailable(RuntimeError):
    """Structured bridge failure for health, preflight, and agent-turn fallback."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "cursor_bridge_unavailable",
        mode: str = "auto",
        fallback: str = CURSOR_BRIDGE_FALLBACK,
        remediation: tuple[str, ...] = CURSOR_BRIDGE_REMEDIATION,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.mode = mode
        self.fallback = fallback
        self.remediation = remediation


@dataclass
class _BridgeEntry:
    client: object
    lock: threading.Lock


_cache: dict[str, _BridgeEntry] = {}
_cache_lock = threading.Lock()


def _abs_workspace(workspace: str) -> str:
    return os.path.abspath(os.path.expanduser(workspace))


def _connection_refused(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "connection refused" in text or "errno 61" in text or "connecterror" in text


def is_transient_bridge_error(exc: BaseException) -> bool:
    """Timeouts / dead bridge — invalidate cache and retry."""
    if _connection_refused(exc):
        return True
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "readtimeout",
            "timed out",
            "timeout",
            "bridge request timed out",
            "bridge request failed",
            "temporarily unavailable",
        )
    )


def _wrap_bridge_error(exc: BaseException, *, mode: str) -> CursorBridgeUnavailable:
    detail = str(exc).strip() or exc.__class__.__name__
    if isinstance(exc, CursorBridgeUnavailable):
        return exc
    code = "cursor_bridge_connection_refused" if _connection_refused(exc) else "cursor_bridge_unavailable"
    if mode == "external":
        code = "cursor_bridge_external_unavailable"
    message = f"Cursor bridge 연결 실패 ({mode}): {detail}"
    return CursorBridgeUnavailable(message, code=code, mode=mode)


def cursor_bridge_failure_payload(
    exc: BaseException | None = None,
    *,
    reason: str | None = None,
) -> dict[str, Any]:
    """User-facing degraded-state fields shared by health/preflight clients."""
    if isinstance(exc, CursorBridgeUnavailable):
        msg = str(exc).strip()
        return {
            "degraded": True,
            "failure_code": exc.code,
            "reason": msg,
            "fallback": exc.fallback,
            "remediation": list(exc.remediation),
        }
    msg = reason or (str(exc).strip() if exc else "") or "Cursor bridge 연결 실패"
    return {
        "degraded": True,
        "failure_code": "cursor_bridge_unavailable",
        "reason": msg,
        "fallback": CURSOR_BRIDGE_FALLBACK,
        "remediation": list(CURSOR_BRIDGE_REMEDIATION),
    }


def _ping_client(client: object) -> None:
    client.ping()  # type: ignore[attr-defined]


def _launch_client(workspace: str) -> object:
    from cursor_sdk import CursorClient

    from agent_lab.subprocess_env import isolated_process_env

    with isolated_process_env():
        return CursorClient.launch_bridge(workspace=workspace)


def _external_client() -> object | None:
    url = os.getenv("CURSOR_SDK_BRIDGE_URL", "").strip()
    token = (os.getenv("CURSOR_SDK_BRIDGE_TOKEN") or os.getenv("CURSOR_SDK_BRIDGE_AUTH_TOKEN") or "").strip()
    if not url:
        return None
    if not token:
        raise CursorBridgeUnavailable(
            "Cursor bridge 연결 실패 (external): CURSOR_SDK_BRIDGE_TOKEN 없음",
            code="cursor_bridge_external_auth_missing",
            mode="external",
        )
    from cursor_sdk import Client

    client = Client(
        base_url=url,
        auth_token=token,
        allow_api_key_env_fallback=True,
    )
    _ping_client(client)
    return client


def invalidate_workspace(workspace: str) -> None:
    ws = _abs_workspace(workspace)
    with _cache_lock:
        entry = _cache.pop(ws, None)
    if entry is None:
        return
    try:
        entry.client.close()  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        from agent_lab.cursor.registry import remove_workspace

        remove_workspace(ws)
    except Exception:
        pass


def _get_or_launch(workspace: str) -> _BridgeEntry:
    ws = _abs_workspace(workspace)
    with _cache_lock:
        entry = _cache.get(ws)
        if entry is not None:
            try:
                _ping_client(entry.client)
                return entry
            except Exception:
                try:
                    entry.client.close()  # type: ignore[attr-defined]
                except Exception:
                    pass
                _cache.pop(ws, None)

        client = _launch_client(ws)
        try:
            from agent_lab.cursor.registry import guess_bridge_pid, register_bridge

            register_bridge(ws, pid=guess_bridge_pid(), mode="auto")
        except Exception:
            pass
        entry = _BridgeEntry(client=client, lock=threading.Lock())
        _cache[ws] = entry
        return entry


@contextmanager
def cursor_sdk_client(workspace: str) -> Iterator[object]:
    """Yield a Cursor SDK client whose bridge workspace matches `workspace`."""
    ws = _abs_workspace(workspace)
    external_url = os.getenv("CURSOR_SDK_BRIDGE_URL", "").strip()
    if external_url:
        try:
            external = _external_client()
        except Exception as exc:
            raise _wrap_bridge_error(exc, mode="external") from exc

        if external is not None:
            yield external
            return

    try:
        entry = _get_or_launch(ws)
    except Exception as exc:
        raise _wrap_bridge_error(exc, mode="auto") from exc

    entry.lock.acquire()
    try:
        yield entry.client
    finally:
        entry.lock.release()


def format_cursor_connect_error(exc: BaseException) -> str:
    if isinstance(exc, CursorBridgeUnavailable):
        payload = cursor_bridge_failure_payload(exc)
        remediation = "; ".join(str(x) for x in list(payload["remediation"]))
        return f"{payload['reason']}\nfallback: {payload['fallback']}\nremediation: {remediation}"
    msg = str(exc).strip() or exc.__class__.__name__
    if _connection_refused(exc):
        return f"{msg}\n{_BRIDGE_HINT}\nfallback: {CURSOR_BRIDGE_FALLBACK}"
    if "Bridge request failed" in msg or "readtimeout" in msg.lower():
        return f"{msg}\n{_BRIDGE_HINT}\nfallback: {CURSOR_BRIDGE_FALLBACK}"
    if "timed out" in msg.lower():
        return (
            f"{msg}\n"
            "bridge 응답 지연 — Cursor 앱 실행 후 Settings에서 'Cursor 재연결' "
            "또는 CURSOR_SDK_BRIDGE_URL 이 죽은 bridge 를 가리키는지 확인\n"
            f"fallback: {CURSOR_BRIDGE_FALLBACK}"
        )
    return msg
