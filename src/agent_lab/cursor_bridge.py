"""Workspace-scoped Cursor SDK bridge lifecycle (avoids stale global bridge / cwd mismatch)."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

_BRIDGE_HINT = (
    "Cursor bridge 연결 실패. 확인: (1) CURSOR_API_KEY 설정 "
    "(2) pip install -e '.[cursor]' "
    "(3) CURSOR_SDK_BRIDGE_URL 이 죽은 IDE bridge 를 가리키면 unset "
    "(4) GUI 앱: ~/.agent-lab/.env 에 CURSOR_SDK_BRIDGE_BIN 절대경로 "
    "(5) Cursor 앱 실행 후 재시도"
)


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


def _ping_client(client: object) -> None:
    client.ping()  # type: ignore[attr-defined]


def _launch_client(workspace: str) -> object:
    from cursor_sdk import CursorClient

    return CursorClient.launch_bridge(workspace=workspace)


def _external_client() -> object | None:
    url = os.getenv("CURSOR_SDK_BRIDGE_URL", "").strip()
    token = (
        os.getenv("CURSOR_SDK_BRIDGE_TOKEN")
        or os.getenv("CURSOR_SDK_BRIDGE_AUTH_TOKEN")
        or ""
    ).strip()
    if not url or not token:
        return None
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
        entry = _BridgeEntry(client=client, lock=threading.Lock())
        _cache[ws] = entry
        return entry


@contextmanager
def cursor_sdk_client(workspace: str) -> Iterator[object]:
    """Yield a Cursor SDK client whose bridge workspace matches `workspace`."""
    ws = _abs_workspace(workspace)
    external = None
    try:
        external = _external_client()
    except Exception:
        external = None

    if external is not None:
        yield external
        return

    entry = _get_or_launch(ws)
    entry.lock.acquire()
    try:
        yield entry.client
    finally:
        entry.lock.release()


def format_cursor_connect_error(exc: BaseException) -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    if _connection_refused(exc):
        return f"{msg}\n{_BRIDGE_HINT}"
    if "Bridge request failed" in msg:
        return f"{msg}\n{_BRIDGE_HINT}"
    return msg
