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
from typing import Any

from agent_lab.agent_models import (  # noqa: E402
    DEFAULT_CLAUDE_MODEL,
    DEFAULT_CLAUDE_REASONING_EFFORT,
)
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
    for candidate in sorted(glob.glob(nvm_glob), reverse=True):
        if Path(candidate).is_file():
            return candidate

    for candidate in (
        home / ".local/bin/claude",
        Path("/opt/homebrew/bin/claude"),
        Path("/usr/local/bin/claude"),
    ):
        if candidate.is_file():
            return str(candidate)

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
    from agent_lab.agent_permissions import normalize_claude_permissions
    from agent_lab.workspace_roots import resolve_workspace_roots

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
        "터미널에서 `claude logout` 후 `claude login` (Claude Pro 구독 OAuth)",
        "수동 테스트: `env -u ANTHROPIC_API_KEY claude -p ping --output-format text --no-session-persistence`",
        "~/.agent-lab/.env 의 ANTHROPIC_API_KEY 는 Room에서 무시됨 — 잘못된 키는 주석 처리",
        "GUI/Tauri: CLAUDE_BIN 절대경로 설정 후 앱 재시작",
    ]
    if "credit balance" in low:
        steps.insert(
            0,
            "ANTHROPIC_API_KEY 잔액 부족 — 구독 OAuth(`claude login`) 사용 또는 Console 크레딧 충전",
        )
    if "401" in detail or "authenticate" in low:
        steps.insert(
            0,
            "OAuth 토큰 만료/손상 — `claude logout && claude login` 으로 headless(`-p`) 인증 갱신",
        )
    return steps


def _format_exec_error(stderr: str, stdout: str) -> str:
    combined = f"{stderr or ''}\n{stdout or ''}"
    errors = [
        ln.strip()
        for ln in combined.splitlines()
        if ln.strip().startswith("ERROR:")
    ]
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
_AUTH_PROBE_TTL_SEC = 120.0


def probe_auth(*, timeout_sec: float = 15.0, use_cache: bool = True) -> tuple[bool, str | None]:
    """Headless auth ping using the same stripped env as Room invoke."""
    if _env_bool("CLAUDE_SKIP_AUTH_PROBE", default=False):
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
    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=_claude_env(),
            cwd=str(Path.home()),
        )
    except subprocess.TimeoutExpired:
        detail = f"claude auth probe timed out ({int(timeout_sec)}s)"
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
        return _optional_timeout_sec("CLAUDE_ROOM_TIMEOUT_SEC", "CLAUDE_TIMEOUT_SEC")
    return _optional_timeout_sec("CLAUDE_TIMEOUT_SEC")


def invoke(
    system: str,
    user: str,
    *,
    permissions: dict | None = None,
    scribe: bool = False,
    room_turn: bool = True,
    on_activity: Callable[[str], None] | None = None,
    session_folder: str | Path | None = None,
    request_structured_envelope: bool = False,
) -> str:
    from agent_lab.agent_permissions import normalize_claude_permissions

    claude = resolve_claude_bin()
    if not claude:
        raise RuntimeError(
            "Claude Code CLI not found. Install: npm i -g @anthropic-ai/claude-code "
            "&& claude login\n"
            "GUI app: add to .env → CLAUDE_BIN=/full/path/to/claude "
            "(e.g. ~/.nvm/versions/node/v24.13.1/bin/claude)"
        )

    perms = normalize_claude_permissions(permissions)
    from agent_lab.workspace_roots import discuss_primary_workspace

    cwd = os.getenv("CLAUDE_CWD") or str(discuss_primary_workspace(perms))
    permission_mode = _permission_mode()
    skip_permissions = _env_bool("CLAUDE_SKIP_PERMISSIONS", default=True)

    system_path = tempfile.mktemp(prefix="agent-lab-claude-sys-", suffix=".txt")
    system_text = system.strip()
    if request_structured_envelope:
        from agent_lab.structured_envelope_adapter import structured_envelope_system_addon

        system_text = f"{system_text}\n\n{structured_envelope_system_addon(compact=True)}"
    # `-p` is required for headless tool loops (Read/Grep/Bash) from a subprocess.
    output_format = "json" if request_structured_envelope else "text"
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

    if scribe:
        model = os.getenv("CLAUDE_SCRIBE_MODEL") or os.getenv(
            "CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL
        )
    else:
        model = os.getenv("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL)
    cmd.extend(["--model", model])

    effort = os.getenv("CLAUDE_SCRIBE_REASONING_EFFORT") if scribe else None
    if not effort:
        effort = os.getenv("CLAUDE_REASONING_EFFORT", DEFAULT_CLAUDE_REASONING_EFFORT)
    if effort:
        cmd.extend(["--effort", effort])

    if budget := os.getenv("CLAUDE_MAX_BUDGET_USD"):
        cmd.extend(["--max-budget-usd", budget.strip()])

    cmd.append(user.strip())

    Path(system_path).write_text(system_text + "\n", encoding="utf-8")

    def _run_once(api_key: str | None) -> str:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=_timeout_sec(room_turn=room_turn),
            env=_claude_env(api_key=api_key),
            cwd=cwd,
        )
        if result.returncode != 0:
            detail = _format_exec_error(result.stderr or "", result.stdout or "")
            if "credit balance is too low" in detail.lower():
                detail = (
                    f"{detail} "
                    "(Agent Lab strips ANTHROPIC_API_KEY for Claude Code CLI; "
                    "if this persists run: claude logout && claude login)"
                )
            raise RuntimeError(
                f"claude -p failed (exit {result.returncode})"
                + (f": {detail}" if detail else "")
            )
        raw = (result.stdout or "").strip()
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
        from agent_lab.agent_hooks_materializer import native_claude_hooks_overlay
        from agent_lab.credential_store import call_with_credential_fallback

        def _run_for_key(api_key: str | None) -> str:
            def _run_with_hooks() -> str:
                with native_claude_hooks_overlay(session_folder, cwd):
                    return _run_once(api_key)

            return retry_call(
                _run_with_hooks,
                max_attempts=retry_max_attempts(room_turn=room_turn),
                base_delay_sec=retry_base_delay_sec(),
                on_retry_label=_on_retry,
            )

        return call_with_credential_fallback(
            "claude",
            _run_for_key,
            allow_oauth_without_key=True,
        )
    finally:
        Path(system_path).unlink(missing_ok=True)


def model_label() -> str:
    model = os.getenv("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL)
    effort = os.getenv("CLAUDE_REASONING_EFFORT", DEFAULT_CLAUDE_REASONING_EFFORT)
    return f"{model} ({effort})"
