"""Invoke Claude Code CLI (subscription / OAuth — not Platform API by default)."""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Mapping

from agent_lab.agent.models import (  # noqa: E402
    DEFAULT_CLAUDE_MODEL,
    DEFAULT_CLAUDE_REASONING_EFFORT,
)
from agent_lab.cost_ledger import chars_to_tokens
from agent_lab.cli_retry import retry_base_delay_sec, retry_call, retry_max_attempts

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_claude_bin() -> str | None:
    """Find claude binary (GUI apps often lack nvm on PATH)."""
    explicit = (os.getenv("CLAUDE_BIN") or "").strip()
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return str(p.resolve())

    found = shutil.which("claude")
    if found:
        return found

    home = Path.home()
    nvm_glob = str(home / ".nvm/versions/node/*/bin/claude")
    for bin_path in sorted(glob.glob(nvm_glob), reverse=True):
        if Path(bin_path).is_file():
            return bin_path

    for path_candidate in (
        home / ".local/bin/claude",
        Path("/opt/homebrew/bin/claude"),
        Path("/usr/local/bin/claude"),
    ):
        if path_candidate.is_file():
            return str(path_candidate)

    return None


def is_available() -> bool:
    return resolve_claude_bin() is not None


def _project_root() -> Path:
    root = os.getenv("AGENT_LAB_ROOT")
    if root and Path(root).is_dir():
        return Path(root).resolve()
    return PROJECT_ROOT


def resolve_claude_roots(permissions: dict[str, Any] | None) -> list[Path]:
    """Directories Claude Code may access via --add-dir."""
    from agent_lab.agent.permissions import normalize_claude_permissions
    from agent_lab.workspace.roots import resolve_workspace_roots

    return resolve_workspace_roots(normalize_claude_permissions(permissions))


def _claude_env(*, api_key: str | None = None) -> dict[str, str]:
    from agent_lab.subprocess_env import subprocess_env

    env = subprocess_env()
    if api_key and api_key.strip():
        env["ANTHROPIC_API_KEY"] = api_key.strip()
    else:
        for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            env.pop(key, None)
    claude = resolve_claude_bin()
    if claude:
        bin_dir = str(Path(claude).parent)
        path = env.get("PATH", "")
        parts = [p for p in path.split(":") if p]
        if bin_dir not in parts:
            env["PATH"] = f"{bin_dir}:{path}" if path else bin_dir
    env.setdefault("HOME", str(Path.home()))
    env.setdefault("TERM", "xterm-256color")
    env.pop("NO_COLOR", None)
    return env


def auth_failure_remediation(detail: str) -> list[str]:
    """Actionable steps when Claude headless auth fails."""
    low = detail.lower()
    steps = [
        "터미널에서 `claude logout` 후 `claude login` (Claude Code OAuth — Room은 API 키 미사용)",
        "수동 테스트: `env -u ANTHROPIC_API_KEY claude -p ping --output-format text --no-session-persistence`",
        "~/.agent-lab/.env 의 ANTHROPIC_API_KEY 는 Claude Room에서 주입하지 않음 — 혼동 방지용 주석 처리 권장",
        "GUI/Tauri: CLAUDE_BIN 절대경로 설정 후 앱 재시작",
    ]
    if "credit balance" in low:
        steps.insert(
            0,
            "API 키 잔액 오류가 OAuth 대신 키로 인증된 경우 — `claude logout && claude login` 으로 OAuth만 사용",
        )
    if "401" in detail or "authenticate" in low:
        steps.insert(
            0,
            "OAuth 토큰 만료/손상 — `claude logout && claude login` 으로 headless(`-p`) 인증 갱신",
        )
    return steps


def _format_exec_error(stderr: str, stdout: str) -> str:
    combined = f"{stderr or ''}\n{stdout or ''}"
    errors = [ln.strip() for ln in combined.splitlines() if ln.strip().startswith("ERROR:")]
    if errors:
        seen: set[str] = set()
        unique: list[str] = []
        for e in errors:
            if e not in seen:
                seen.add(e)
                unique.append(e)
        detail = " ".join(unique)
    else:
        detail = combined.strip()
    if "usage limit" in detail.lower() or "credit balance" in detail.lower():
        detail = detail[:600]
    elif "Reading additional input from stdin" in detail:
        detail = "Claude CLI stdin/prompt handling failed."
    else:
        detail = detail[:800] if detail else "unknown error"
    low = detail.lower()
    if "401" in detail or "authenticate" in low or "credit balance" in low:
        hint = auth_failure_remediation(detail)[0]
        return f"{detail} — {hint}"
    return detail


_AUTH_PROBE_CACHE: tuple[float, bool, str | None] | None = None
_AUTH_PROBE_TTL_SEC = 300.0
_AUTH_STATUS_CACHE: tuple[float, bool, str | None] | None = None
_AUTH_STATUS_TTL_SEC = 60.0
_DEFAULT_PROBE_TIMEOUT_SEC = 25.0
_DEFAULT_ROOM_TIMEOUT_SEC = 900
_DEFAULT_ROOM_IDLE_TIMEOUT_SEC = 45.0


def invalidate_claude_auth_cache() -> None:
    """Clear cached auth status/probe results after invoke failures or reconnect."""
    global _AUTH_PROBE_CACHE, _AUTH_STATUS_CACHE
    _AUTH_PROBE_CACHE = None
    _AUTH_STATUS_CACHE = None


def format_claude_auth_status_detail(raw: str, *, logged_in: bool) -> str:
    """Human-readable summary of ``claude auth status`` JSON for UI surfaces."""
    payload: dict[str, Any] | None = None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None
    if logged_in:
        if isinstance(payload, dict):
            email = str(payload.get("email") or "").strip()
            if email:
                return f"OAuth 연결됨 ({email})"
        return "OAuth 연결됨"
    return "OAuth 미로그인 — /login 또는 claude auth login"


def _is_auth_failure(detail: str) -> bool:
    low = detail.lower()
    return "401" in detail or "authenticate" in low or "credit balance" in low


def _is_usage_limit_detail(detail: str) -> bool:
    from agent_lab.agent.availability import is_usage_limit_error

    return is_usage_limit_error(detail)


def _room_idle_timeout_sec() -> float:
    raw = (os.getenv("CLAUDE_ROOM_IDLE_TIMEOUT_SEC") or "").strip()
    if raw:
        try:
            return max(5.0, float(raw))
        except ValueError:
            pass
    return _DEFAULT_ROOM_IDLE_TIMEOUT_SEC


def claude_auth_logged_in(*, use_cache: bool = True) -> tuple[bool, str | None]:
    """Fast OAuth session check via `claude auth status` (no headless -p probe)."""
    if os.getenv("AGENT_LAB_MOCK_AGENTS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True, None

    global _AUTH_STATUS_CACHE
    now = time.time()
    if use_cache and _AUTH_STATUS_CACHE is not None:
        cached_at, ok, detail = _AUTH_STATUS_CACHE
        if now - cached_at < _AUTH_STATUS_TTL_SEC:
            return ok, detail

    claude = resolve_claude_bin()
    if not claude:
        detail = "claude CLI not found"
        _AUTH_STATUS_CACHE = (now, False, detail)
        return False, detail

    try:
        result = subprocess.run(
            [claude, "auth", "status"],
            capture_output=True,
            text=True,
            timeout=8.0,
            env=_claude_env(),
            cwd=str(Path.home()),
        )
    except subprocess.TimeoutExpired:
        detail = "claude auth status timed out"
        _AUTH_STATUS_CACHE = (now, False, detail)
        return False, detail
    except OSError as exc:
        detail = str(exc)[:200]
        _AUTH_STATUS_CACHE = (now, False, detail)
        return False, detail

    raw = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        detail = raw[:200] or f"claude auth status exit {result.returncode}"
        _AUTH_STATUS_CACHE = (now, False, detail)
        return False, detail

    try:
        payload = json.loads(raw)
        logged_in = bool(payload.get("loggedIn"))
    except json.JSONDecodeError:
        logged_in = '"loggedIn": true' in raw or '"loggedIn":true' in raw

    if logged_in:
        _AUTH_STATUS_CACHE = (now, True, None)
        return True, None

    detail = format_claude_auth_status_detail(raw, logged_in=False)
    _AUTH_STATUS_CACHE = (now, False, detail)
    return False, detail


def _skip_headless_probe() -> bool:
    return _env_bool("AGENT_LAB_CLAUDE_SKIP_HEADLESS_PROBE", default=False) or _env_bool(
        "CLAUDE_SKIP_AUTH_PROBE",
        default=False,
    )


def probe_timeout_sec() -> float:
    raw = (os.getenv("AGENT_LAB_CLAUDE_PROBE_TIMEOUT_SEC") or "").strip()
    if raw:
        try:
            return max(5.0, float(raw))
        except ValueError:
            pass
    return _DEFAULT_PROBE_TIMEOUT_SEC


def ensure_claude_headless_ready(*, use_cache: bool = True) -> None:
    """Fail fast when OAuth status lies but headless ``-p`` is broken (cached)."""
    if _skip_headless_probe():
        logged_in, detail = claude_auth_logged_in(use_cache=use_cache)
        if not logged_in:
            raise RuntimeError(detail or "claude OAuth not logged in")
        return
    ok, detail = probe_auth(timeout_sec=probe_timeout_sec(), use_cache=use_cache)
    if not ok:
        raise RuntimeError(detail or "claude headless auth failed")


def probe_auth(*, timeout_sec: float | None = None, use_cache: bool = True) -> tuple[bool, str | None]:
    """Headless auth ping using the same stripped env as Room invoke."""
    if _skip_headless_probe():
        return True, None
    if os.getenv("AGENT_LAB_MOCK_AGENTS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True, None

    global _AUTH_PROBE_CACHE
    now = time.time()
    if use_cache and _AUTH_PROBE_CACHE is not None:
        cached_at, ok, detail = _AUTH_PROBE_CACHE
        if now - cached_at < _AUTH_PROBE_TTL_SEC:
            return ok, detail

    logged_in, login_detail = claude_auth_logged_in(use_cache=use_cache)
    if not logged_in:
        _AUTH_PROBE_CACHE = (now, False, login_detail)
        return False, login_detail

    claude = resolve_claude_bin()
    if not claude:
        detail = "claude CLI not found"
        _AUTH_PROBE_CACHE = (now, False, detail)
        return False, detail

    cmd = [
        claude,
        "-p",
        "Reply with exactly: AUTH_OK",
        "--output-format",
        "text",
        "--no-session-persistence",
        "--permission-mode",
        "bypassPermissions",
        "--dangerously-skip-permissions",
        "--tools",
        "",
    ]
    deadline = probe_timeout_sec() if timeout_sec is None else timeout_sec
    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=deadline,
            env=_claude_env(),
            cwd=str(Path.home()),
        )
    except subprocess.TimeoutExpired:
        detail = f"claude auth probe timed out ({int(deadline)}s)"
        _AUTH_PROBE_CACHE = (now, False, detail)
        return False, detail
    except OSError as exc:
        detail = str(exc)[:200]
        _AUTH_PROBE_CACHE = (now, False, detail)
        return False, detail

    if result.returncode != 0:
        detail = _format_exec_error(result.stderr or "", result.stdout or "")
        _AUTH_PROBE_CACHE = (now, False, detail)
        return False, detail

    text = (result.stdout or "").strip()
    if not text:
        detail = "claude auth probe returned empty output"
        _AUTH_PROBE_CACHE = (now, False, detail)
        return False, detail

    _AUTH_PROBE_CACHE = (now, True, None)
    return True, None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _permission_mode() -> str:
    """Headless room turns need bypassPermissions when skip-permissions is on."""
    if _env_bool("CLAUDE_SKIP_PERMISSIONS", default=True):
        return "bypassPermissions"
    mode = (os.getenv("CLAUDE_PERMISSION_MODE") or "acceptEdits").strip()
    allowed = {
        "acceptEdits",
        "auto",
        "bypassPermissions",
        "default",
        "dontAsk",
        "plan",
    }
    return mode if mode in allowed else "acceptEdits"


def _optional_timeout_sec(*env_keys: str) -> int | None:
    for key in env_keys:
        raw = (os.getenv(key) or "").strip()
        if raw:
            return int(raw)
    return None


def _timeout_sec(*, room_turn: bool) -> int | None:
    if room_turn:
        explicit = _optional_timeout_sec("CLAUDE_ROOM_TIMEOUT_SEC", "CLAUDE_TIMEOUT_SEC")
        return explicit if explicit is not None else _DEFAULT_ROOM_TIMEOUT_SEC
    return _optional_timeout_sec("CLAUDE_TIMEOUT_SEC")


def _resolve_claude_mcp_config(
    session_folder: Path | None,
    permissions: dict | None,
    *,
    inbox_mcp: bool,
) -> str | None:
    """Merge inbox MCP + execute-plugin overlays for Claude ``--mcp-config``."""
    paths: list[Path] = []
    if inbox_mcp and session_folder is not None:
        from agent_lab.cursor.inbox_mcp import (
            build_claude_inbox_mcp_overlay,
            inbox_mcp_build_kwargs,
        )

        paths.append(
            build_claude_inbox_mcp_overlay(
                session_folder,
                **inbox_mcp_build_kwargs(permissions),
            )
        )
    if session_folder is not None:
        from agent_lab.cursor.session_metrics_mcp import (
            build_claude_session_metrics_overlay,
            session_metrics_mcp_enabled,
        )

        if session_metrics_mcp_enabled():
            paths.append(build_claude_session_metrics_overlay(session_folder))
    if (permissions or {}).get("_execute_plugins") and session_folder is not None:
        from agent_lab.session.plugin_runtime import resolve_claude_mcp_config_path

        cfg = resolve_claude_mcp_config_path(session_folder)
        if cfg:
            paths.append(Path(cfg))
    if not paths:
        return None
    if len(paths) == 1:
        return str(paths[0].resolve())
    assert session_folder is not None
    servers: dict[str, Any] = {}
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        servers.update(data.get("mcpServers") or {})
    merged = session_folder / ".agent-lab" / "claude-mcp-merged.json"
    merged.parent.mkdir(parents=True, exist_ok=True)
    merged.write_text(
        json.dumps({"mcpServers": servers}, indent=2) + "\n",
        encoding="utf-8",
    )
    return str(merged.resolve())


def invoke(
    system: str,
    user: str,
    *,
    permissions: dict | None = None,
    scribe: bool = False,
    room_turn: bool = True,
    model: str | None = None,
    on_activity: Callable[[str], None] | None = None,
    on_bridge_event: Callable[[str, dict[str, Any]], None] | None = None,
    session_folder: str | Path | None = None,
    request_structured_envelope: bool = False,
    inbox_mcp: bool = False,
) -> str:
    from agent_lab.agent.permissions import normalize_claude_permissions

    claude = resolve_claude_bin()
    if not claude:
        raise RuntimeError(
            "Claude Code CLI not found. Install: npm i -g @anthropic-ai/claude-code "
            "&& claude login\n"
            "GUI app: add to .env → CLAUDE_BIN=/full/path/to/claude "
            "(e.g. ~/.nvm/versions/node/v24.13.1/bin/claude)"
        )

    perms = normalize_claude_permissions(permissions)
    from agent_lab.workspace.roots import discuss_primary_workspace

    cwd = os.getenv("CLAUDE_CWD") or str(discuss_primary_workspace(perms))
    permission_mode = _permission_mode()
    skip_permissions = _env_bool("CLAUDE_SKIP_PERMISSIONS", default=True)

    system_path = tempfile.mktemp(prefix="agent-lab-claude-sys-", suffix=".txt")
    system_text = system.strip()
    if request_structured_envelope:
        from agent_lab.structured_envelope_adapter import structured_envelope_system_addon

        system_text = f"{system_text}\n\n{structured_envelope_system_addon(compact=True)}"
    # `-p` is required for headless tool loops (Read/Grep/Bash) from a subprocess.
    use_stream = on_bridge_event is not None and not request_structured_envelope
    if request_structured_envelope:
        output_format = "json"
    elif use_stream:
        output_format = "stream-json"
    else:
        output_format = "text"
    cmd: list[str] = [
        claude,
        "-p",
        "--output-format",
        output_format,
        "--no-session-persistence",
        "--append-system-prompt-file",
        system_path,
        "--permission-mode",
        permission_mode,
    ]
    if use_stream:
        cmd.extend(["--verbose", "--include-partial-messages"])

    if skip_permissions:
        cmd.append("--dangerously-skip-permissions")

    # --bare skips OAuth/keychain (needs API key) — default off; set CLAUDE_BARE=1 only if you use API key auth.
    if _env_bool("CLAUDE_BARE", default=False):
        cmd.append("--bare")

    if _env_bool("CLAUDE_DISABLE_TOOLS", default=False):
        cmd.extend(["--tools", ""])
    else:
        cmd.extend(["--tools", "default"])

    for root in resolve_claude_roots(perms):
        cmd.extend(["--add-dir", str(root)])

    session_path = Path(session_folder).expanduser() if session_folder else None
    mcp_cfg = _resolve_claude_mcp_config(session_path, perms, inbox_mcp=inbox_mcp)
    if mcp_cfg:
        cmd.extend(["--mcp-config", mcp_cfg])
    elif perms.get("_execute_plugins"):
        from agent_lab.session.plugin_runtime import claude_execute_extra_args

        cmd.extend(claude_execute_extra_args(perms))

    if scribe:
        resolved_model = (
            (model or "").strip()
            or os.getenv("CLAUDE_SCRIBE_MODEL")
            or os.getenv("CLAUDE_MODEL")
            or DEFAULT_CLAUDE_MODEL
        )
    else:
        resolved_model = (model or "").strip() or os.getenv("CLAUDE_MODEL") or DEFAULT_CLAUDE_MODEL
    cmd.extend(["--model", str(resolved_model)])

    effort = os.getenv("CLAUDE_SCRIBE_REASONING_EFFORT") if scribe else None
    if not effort:
        effort = os.getenv("CLAUDE_REASONING_EFFORT", DEFAULT_CLAUDE_REASONING_EFFORT)
    if effort:
        cmd.extend(["--effort", effort])

    if budget := os.getenv("CLAUDE_MAX_BUDGET_USD"):
        cmd.extend(["--max-budget-usd", budget.strip()])

    cmd.append(user.strip())

    Path(system_path).write_text(system_text + "\n", encoding="utf-8")

    if room_turn:
        ensure_claude_headless_ready(use_cache=True)

    def _run_once(api_key: str | None) -> str:
        if use_stream:
            assert on_bridge_event is not None
            return _run_claude_stream(
                cmd,
                on_bridge_event=on_bridge_event,
                on_activity=on_activity,
                timeout=_timeout_sec(room_turn=room_turn),
                api_key=api_key,
                cwd=cwd,
            )
        import time

        from agent_lab.run.control import (
            RoomRunCancelled,
            is_cancelled,
            register_child_process,
            unregister_child_process,
        )

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_claude_env(api_key=api_key),
            cwd=cwd,
        )
        register_child_process(proc)
        deadline = _timeout_sec(room_turn=room_turn)
        started = time.monotonic()
        try:
            while proc.poll() is None:
                if is_cancelled():
                    proc.kill()
                    proc.wait(timeout=5)
                    raise RoomRunCancelled("run cancelled by user")
                if deadline is not None and time.monotonic() - started >= deadline:
                    proc.kill()
                    proc.wait(timeout=5)
                    raise subprocess.TimeoutExpired(cmd, deadline)
                from agent_lab.backoff_policy import wait as _backoff_wait

                _backoff_wait(1, base_sec=0.2)
            stdout, stderr = proc.communicate()
        finally:
            unregister_child_process(proc)
        if proc.returncode != 0:
            if is_cancelled():
                raise RoomRunCancelled("run cancelled by user")
            detail = _format_exec_error(stderr or "", stdout or "")
            if "credit balance is too low" in detail.lower():
                detail = f"{detail} (Claude Room uses OAuth only — run: claude logout && claude login)"
            if _is_auth_failure(detail):
                invalidate_claude_auth_cache()
            raise RuntimeError(f"claude -p failed (exit {proc.returncode})" + (f": {detail}" if detail else ""))
        raw = (stdout or "").strip()
        if not raw:
            raise RuntimeError("claude -p returned empty output")
        if request_structured_envelope:
            from agent_lab.structured_envelope_adapter import parse_claude_json_stdout

            structured, body = parse_claude_json_stdout(raw)
            if structured is not None:
                return json.dumps(structured, ensure_ascii=False) + "\n" + (body or "")
            return body or raw
        return raw

    def _on_retry(attempt: int, max_attempts: int, _reason: str) -> None:
        if on_activity:
            on_activity(f"재시도 {attempt}/{max_attempts} — Claude CLI 일시 오류")

    try:
        from agent_lab.agent.hooks_materializer import native_claude_hooks_overlay

        def _run_oauth_only() -> str:
            def _run_with_hooks() -> str:
                with native_claude_hooks_overlay(session_folder, cwd):
                    return _run_once(None)

            return retry_call(
                _run_with_hooks,
                max_attempts=retry_max_attempts(room_turn=room_turn),
                base_delay_sec=retry_base_delay_sec(),
                on_retry_label=_on_retry,
            )

        # Claude Code Room path: OAuth/keychain only — never inject API keys from credential store.
        return _run_oauth_only()
    finally:
        Path(system_path).unlink(missing_ok=True)


def _claude_usage_payload_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """Extract provider usage from a stream-json ``result`` event (shape varies by CLI version)."""
    usage: dict[str, Any] = {}
    raw_usage = event.get("usage")
    if isinstance(raw_usage, Mapping):
        usage = dict(raw_usage)
    elif isinstance(event.get("message"), Mapping):
        msg_usage = event["message"].get("usage")
        if isinstance(msg_usage, Mapping):
            usage = dict(msg_usage)
    cost = event.get("total_cost_usd")
    if cost is None:
        cost = event.get("cost_usd")
    if not usage and cost is None:
        return None
    payload: dict[str, Any] = {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
        "total_cost_usd": cost,
        "model": event.get("model") or os.getenv("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL),
        "usage_source": "provider",
    }
    if not any(
        payload.get(k)
        for k in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "total_cost_usd",
        )
    ):
        return None
    return payload


def _emit_claude_usage(
    event: dict[str, Any],
    on_bridge_event: Callable[[str, dict[str, Any]], None] | None,
    *,
    result_text: str = "",
) -> None:
    """Surface token/cost from a stream-json ``result`` event into the Room bridge."""
    if on_bridge_event is None:
        return
    payload = _claude_usage_payload_from_event(event)
    if payload is None and result_text.strip():
        payload = {
            "input_tokens": 0,
            "output_tokens": max(1, chars_to_tokens(len(result_text))),
            "model": event.get("model") or os.getenv("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL),
            "usage_source": "estimated",
        }
    if payload is None:
        return
    try:
        on_bridge_event("usage", payload)
    except Exception:
        # Usage accounting must never break the turn.
        pass


def _run_claude_stream(
    cmd: list[str],
    *,
    on_bridge_event: Callable[[str, dict[str, Any]], None],
    on_activity: Callable[[str], None] | None,
    timeout: int | None,
    api_key: str | None,
    cwd: str,
) -> str:
    """Read Claude ``stream-json`` stdout and emit Room bridge events."""
    import select
    import time

    from agent_lab.agent.stream_parser import parse_claude_json_event
    from agent_lab.run.control import (
        RoomRunCancelled,
        is_cancelled,
        register_child_process,
        unregister_child_process,
    )

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_claude_env(api_key=api_key),
        cwd=cwd,
    )
    register_child_process(proc)
    stdout = proc.stdout
    stderr = proc.stderr
    assert stdout is not None
    assert stderr is not None
    stderr_parts: list[str] = []
    result_text = ""
    seen_text_delta = False
    response_started = False
    started = time.monotonic()
    last_activity_at = started
    last_heartbeat_at = started
    heartbeat_interval = 8.0
    idle_timeout = _room_idle_timeout_sec() if timeout is not None else None
    try:
        while True:
            if is_cancelled():
                proc.kill()
                proc.wait(timeout=5)
                raise RoomRunCancelled("run cancelled by user")
            now = time.monotonic()
            if timeout is not None and not response_started and now - started >= timeout:
                proc.kill()
                proc.wait(timeout=5)
                raise subprocess.TimeoutExpired(cmd, timeout)
            if (
                idle_timeout is not None
                and not response_started
                and now - last_activity_at >= idle_timeout
            ):
                combined = "".join(stderr_parts)
                if _is_usage_limit_detail(combined):
                    proc.kill()
                    proc.wait(timeout=5)
                    detail = _format_exec_error(combined, result_text)
                    raise RuntimeError(
                        "claude -p failed (usage limit)"
                        + (f": {detail}" if detail else "")
                    )
            if on_activity and now - last_heartbeat_at >= heartbeat_interval:
                idle_for = now - last_activity_at
                if not response_started or idle_for >= heartbeat_interval:
                    on_activity("[claude · working…]")
                    last_heartbeat_at = now
                    last_activity_at = now
            if proc.poll() is not None:
                if not select.select([stdout, stderr], [], [], 0)[0]:
                    break
            ready, _, _ = select.select([stdout, stderr], [], [], 0.25)
            if stderr in ready:
                err_chunk = stderr.read()
                if err_chunk:
                    stderr_parts.append(err_chunk)
                    combined = "".join(stderr_parts)
                    if _is_usage_limit_detail(combined):
                        proc.kill()
                        proc.wait(timeout=5)
                        detail = _format_exec_error(combined, result_text)
                        raise RuntimeError(
                            "claude -p failed (usage limit)"
                            + (f": {detail}" if detail else "")
                        )
                    if _is_auth_failure(err_chunk):
                        proc.kill()
                        proc.wait(timeout=5)
                        detail = _format_exec_error(combined, result_text)
                        invalidate_claude_auth_cache()
                        raise RuntimeError("claude -p failed (auth)" + (f": {detail}" if detail else ""))
            if stdout not in ready:
                continue
            line = stdout.readline()
            if not line:
                # Child exited but select can still report stdout readable (EOF spin).
                if proc.poll() is not None:
                    break
                continue
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            evt_type = str(event.get("type") or "")
            if evt_type == "stream_event":
                inner_raw = event.get("event")
                inner: dict[str, Any] = inner_raw if isinstance(inner_raw, dict) else {}
                delta_raw = inner.get("delta")
                delta: dict[str, Any] = delta_raw if isinstance(delta_raw, dict) else {}
                if str(delta.get("type") or "") == "text_delta" and str(delta.get("text") or ""):
                    seen_text_delta = True
                    response_started = True
                    last_activity_at = time.monotonic()
            if evt_type in {"stream_event", "assistant"}:
                response_started = True
                last_activity_at = time.monotonic()
            for kind, data in parse_claude_json_event(event):
                if kind == "text" and evt_type == "assistant" and seen_text_delta:
                    continue
                if kind in {"tool_start", "activity", "text"}:
                    last_activity_at = time.monotonic()
                on_bridge_event(kind, data)
            if event.get("type") == "result":
                res = event.get("result")
                if isinstance(res, str) and res.strip():
                    result_text = res.strip()
                _emit_claude_usage(event, on_bridge_event, result_text=result_text)
    finally:
        unregister_child_process(proc)
    if proc.stderr:
        stderr_parts.append(proc.stderr.read() or "")
    if proc.poll() is None:
        proc.wait()
    if proc.returncode not in (0, None):
        if is_cancelled():
            raise RoomRunCancelled("run cancelled by user")
        detail = _format_exec_error("".join(stderr_parts), result_text)
        if _is_auth_failure(detail):
            invalidate_claude_auth_cache()
        raise RuntimeError(f"claude -p failed (exit {proc.returncode})" + (f": {detail}" if detail else ""))
    if not result_text:
        raise RuntimeError("claude stream-json returned empty result")
    return result_text


def model_label() -> str:
    model = os.getenv("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL)
    effort = os.getenv("CLAUDE_REASONING_EFFORT", DEFAULT_CLAUDE_REASONING_EFFORT)
    return f"{model} ({effort})"
