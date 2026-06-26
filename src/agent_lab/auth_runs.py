"""Allowlisted PTY authentication runs for CLI-backed providers."""

from __future__ import annotations

import os
import pty
import re
import select
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from agent_lab.provider_registry import ProviderSpec, all_providers, get_provider
from agent_lab.credential_store import (
    _PROVIDER_ENV,
    _PROVIDER_FALLBACK_ENV,
    get_provider_accounts,
    mask_secret,
    public_credentials_payload,
)
from agent_lab.subprocess_env import subprocess_env

AuthAction = Literal["login", "logout"]
AuthRunStatus = Literal["running", "completed", "failed", "cancelled"]

_URL_RE = re.compile(r"https?://[^\s\x1b<>]+")
_runs: dict[str, "AuthRun"] = {}
_runs_lock = threading.Lock()
_status_cache: dict[str, tuple[float, str, str | None]] = {}
_status_refreshing: set[str] = set()
_status_generation: dict[str, int] = {}
_status_lock = threading.Lock()


@dataclass(slots=True)
class AuthRun:
    """Mutable process state shared by the worker thread and WebSocket."""

    id: str
    provider_id: str
    action: AuthAction
    pid: int
    fd: int
    status: AuthRunStatus = "running"
    detail: str | None = None
    events: deque[dict[str, Any]] = field(default_factory=deque)
    lock: threading.Lock = field(default_factory=threading.Lock)
    created_at: float = field(default_factory=time.monotonic)


def _argv(spec: ProviderSpec, action: AuthAction) -> tuple[str, ...]:
    return spec.login_argv if action == "login" else spec.logout_argv


def _resolved_argv(spec: ProviderSpec, action: AuthAction) -> list[str]:
    if os.getenv("AGENT_LAB_MOCK_AGENTS", "").strip().lower() in {"1", "true", "yes", "on"}:
        try:
            delay = min(max(float(os.getenv("AGENT_LAB_AUTH_MOCK_DELAY_S", "0")), 0.0), 10.0)
        except ValueError:
            delay = 0.0
        exit_code = 1 if os.getenv("AGENT_LAB_AUTH_MOCK_RESULT", "success") == "failed" else 0
        script = (
            f"import time; time.sleep({delay!r}); "
            f"print('mock {action} {spec.id} complete'); raise SystemExit({exit_code})"
        )
        return [sys.executable, "-c", script]
    argv = _argv(spec, action)
    if not argv:
        raise RuntimeError(f"{spec.id} does not support {action}")
    executable = shutil.which(argv[0])
    if executable is None:
        raise RuntimeError(f"{argv[0]} CLI not found")
    return [executable, *argv[1:]]


def _safe_auth_url(spec: ProviderSpec, raw: str) -> str | None:
    parsed = urlparse(raw.rstrip(".,);]"))
    if parsed.scheme != "https" or parsed.hostname is None:
        return None
    hostname = parsed.hostname.lower()
    if any(hostname == host or hostname.endswith(f".{host}") for host in spec.browser_hosts):
        return parsed.geturl()
    return None


def _append_event(run: AuthRun, event: dict[str, Any]) -> None:
    with run.lock:
        run.events.append(event)


def _watch_run(run: AuthRun, spec: ProviderSpec) -> None:
    chunks: list[str] = []
    while True:
        try:
            ready, _, _ = select.select([run.fd], [], [], 0.1)
            if ready:
                try:
                    chunk = os.read(run.fd, 4096).decode("utf-8", errors="replace")
                except OSError:
                    chunk = ""  # EIO when PTY slave closes
                if chunk:
                    chunks.append(chunk)
                    _append_event(run, {"type": "output", "data": chunk})
                    for raw_url in _URL_RE.findall(chunk):
                        safe_url = _safe_auth_url(spec, raw_url)
                        if safe_url:
                            _append_event(run, {"type": "auth_url", "url": safe_url})
        except OSError:
            pass  # select failure; fall through to waitpid
        try:
            pid, status = os.waitpid(run.pid, os.WNOHANG)
        except OSError:
            pid, status = run.pid, 0  # ECHILD: already reaped, assume success
        if pid == 0:
            continue
        with run.lock:
            if run.status == "cancelled":
                event_type = None
            elif os.waitstatus_to_exitcode(status) == 0:
                run.status = "completed"
                event_type = "completed"
            else:
                run.status = "failed"
                run.detail = "".join(chunks)[-500:].strip() or "authentication command failed"
                event_type = "failed"
            if event_type is not None:
                run.events.append({"type": event_type, "detail": run.detail})
        try:
            os.close(run.fd)
        except OSError:
            pass
        revalidate_provider_status(spec.id)
        return


def start_auth_run(provider_id: str, action: AuthAction = "login") -> dict[str, str]:
    spec = get_provider(provider_id)
    if spec is None:
        raise RuntimeError(f"unknown provider: {provider_id}")
    argv = _resolved_argv(spec, action)
    master_fd, slave_fd = pty.openpty()
    env = subprocess_env(TERM="xterm-256color", HOME=str(Path.home()))
    process = subprocess.Popen(
        argv,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        cwd=Path.home(),
        env=env,
        start_new_session=True,
        close_fds=True,
    )
    os.close(slave_fd)
    run = AuthRun(
        id=uuid.uuid4().hex,
        provider_id=provider_id,
        action=action,
        pid=process.pid,
        fd=master_fd,
    )
    with _runs_lock:
        cutoff = time.monotonic() - 600
        expired = [
            run_id
            for run_id, existing in _runs.items()
            if existing.status != "running" and existing.created_at < cutoff
        ]
        for run_id in expired:
            del _runs[run_id]
        _runs[run.id] = run
    threading.Thread(target=_watch_run, args=(run, spec), name=f"auth-run-{run.id[:8]}", daemon=True).start()
    return {"id": run.id, "provider_id": provider_id, "action": action, "status": run.status}


def get_auth_run(run_id: str) -> AuthRun | None:
    with _runs_lock:
        return _runs.get(run_id)


def drain_auth_events(run: AuthRun) -> list[dict[str, Any]]:
    with run.lock:
        events = list(run.events)
        run.events.clear()
        return events


def send_auth_input(run: AuthRun, data: str) -> None:
    if run.status == "running":
        try:
            os.write(run.fd, data.encode())
        except OSError:
            return


def cancel_auth_run(run: AuthRun) -> None:
    with run.lock:
        if run.status != "running":
            return
        run.status = "cancelled"
        run.events.append({"type": "cancelled", "detail": None})
    try:
        os.killpg(run.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def provider_login_status(provider_id: str) -> tuple[str, str | None]:
    """Probe current auth state for a provider (lightweight, no side effects)."""
    spec = get_provider(provider_id)
    if spec is None:
        return "unknown", None
    return _probe_provider_status(spec)


def _probe_provider_status(spec: ProviderSpec) -> tuple[str, str | None]:
    if os.getenv("AGENT_LAB_MOCK_AGENTS", "").strip().lower() in {"1", "true", "yes", "on"}:
        return "logged_in", "mock"
    if not spec.status_argv:
        return ("logged_in", "local") if spec.always_available else ("logged_out", None)
    executable = shutil.which(spec.status_argv[0])
    if executable is None:
        return "unavailable", f"{spec.status_argv[0]} CLI not found"
    try:
        result = subprocess.run(
            [executable, *spec.status_argv[1:]],
            capture_output=True,
            text=True,
            timeout=8,
            cwd=Path.home(),
            env=subprocess_env(HOME=str(Path.home())),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "error", str(exc)[:200]
    detail = f"{result.stdout or ''}\n{result.stderr or ''}".strip()[:240]
    return ("logged_in", detail) if result.returncode == 0 else ("logged_out", detail)


def _refresh_status_worker(spec: ProviderSpec, generation: int) -> None:
    state, detail = _probe_provider_status(spec)
    with _status_lock:
        if _status_generation.get(spec.id, 0) != generation:
            return
        _status_cache[spec.id] = (time.monotonic(), state, detail)
        _status_refreshing.discard(spec.id)


def refresh_provider_status(provider_id: str) -> None:
    spec = get_provider(provider_id)
    if spec is None:
        return
    with _status_lock:
        if provider_id in _status_refreshing:
            return
        _status_refreshing.add(provider_id)
        generation = _status_generation.get(provider_id, 0)
    threading.Thread(
        target=_refresh_status_worker,
        args=(spec, generation),
        name=f"auth-status-{provider_id}",
        daemon=True,
    ).start()


def revalidate_provider_status(provider_id: str) -> None:
    spec = get_provider(provider_id)
    if spec is None:
        return
    with _status_lock:
        generation = _status_generation.get(provider_id, 0) + 1
        _status_generation[provider_id] = generation
        _status_cache.pop(provider_id, None)
        _status_refreshing.add(provider_id)
    threading.Thread(
        target=_refresh_status_worker,
        args=(spec, generation),
        name=f"auth-status-{provider_id}",
        daemon=True,
    ).start()


def provider_status_payload() -> dict[str, Any]:
    credential_rows = {row["id"]: row for row in public_credentials_payload().get("agents", [])}
    is_mock = os.getenv("AGENT_LAB_MOCK_AGENTS", "").strip().lower() in {"1", "true", "yes", "on"}
    rows: list[dict[str, Any]] = []
    for spec in all_providers():
        installed = is_mock or bool(spec.status_argv and shutil.which(spec.status_argv[0]))
        detail: str | None = None
        with _status_lock:
            cached = _status_cache.get(spec.id)
        state = cached[1] if cached else "checking"
        detail = cached[2] if cached else None
        if cached is None or time.monotonic() - cached[0] > 30:
            refresh_provider_status(spec.id)

        # Build a credential row for non-legacy providers (kimi/local) from accounts.toml.
        accounts = get_provider_accounts(spec.id)
        can_store_secret = spec.auth_kind in ("api", "local")
        first_secret = ""
        if can_store_secret:
            for acct in accounts:
                s = str(acct.get("secret_or_profile_ref") or acct.get("secret") or "").strip()
                if s:
                    first_secret = s
                    break
        credential = credential_rows.get(spec.id)
        if credential is None:
            oauth_only = "api" not in spec.supported_auth and "local" not in spec.supported_auth
            credential = {
                "id": spec.id,
                "label": spec.label,
                "env_primary": _PROVIDER_ENV.get(spec.id, ""),
                "env_fallback": _PROVIDER_FALLBACK_ENV.get(spec.id, ""),
                "primary_label": "메인",
                "fallback_label": "서브",
                "oauth_only": oauth_only,
                "has_primary": bool(first_secret),
                "has_fallback": False,
                "primary_masked": mask_secret(first_secret) if first_secret else None,
                "fallback_masked": None,
                "stored_primary": bool(first_secret),
                "stored_fallback": False,
            }
        elif can_store_secret and first_secret and not credential.get("has_primary"):
            credential = {**credential, "has_primary": True, "primary_masked": mask_secret(first_secret)}

        if spec.always_available:
            state = "logged_in"
        elif spec.auth_kind == "api":
            if credential.get("has_primary") or credential.get("has_fallback"):
                state = "logged_in"
            elif "oauth" not in spec.supported_auth:
                state = "logged_out"
        elif not installed:
            state = "unavailable"
        rows.append(
            {
                "id": spec.id,
                "label": spec.label,
                "auth_methods": sorted(spec.supported_auth),
                "account_mode": spec.account_mode,
                "installed": installed or spec.always_available,
                "state": state,
                "detail": detail,
                "accounts": credential,
            }
        )
    from agent_lab.codex_oauth import load_meta, profile_exists

    codex = next((row for row in rows if row["id"] == "codex"), None)
    if codex is not None:
        meta = load_meta()
        codex["profiles"] = {
            "has_primary": profile_exists("primary"),
            "has_fallback": profile_exists("fallback"),
            "primary_label": meta["primary_label"],
            "fallback_label": meta["fallback_label"],
        }
    return {"ok": True, "providers": rows}


def capture_codex_run(run_id: str, slot: Literal["primary", "fallback"], *, confirm: bool) -> dict[str, Any]:
    run = get_auth_run(run_id)
    if run is None or run.provider_id != "codex" or run.status != "completed":
        raise RuntimeError("completed Codex login run required")
    from agent_lab.codex_oauth import capture_profile, profile_exists

    if profile_exists(slot) and not confirm:
        raise RuntimeError(f"{slot} profile already exists; confirm replacement")
    return capture_profile(slot)
