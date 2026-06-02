"""Invoke Claude Code CLI (subscription / OAuth — not Platform API by default)."""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from agent_lab.agent_models import (  # noqa: E402
    DEFAULT_CLAUDE_MODEL,
    DEFAULT_CLAUDE_REASONING_EFFORT,
)

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


def _claude_env() -> dict[str, str]:
    env = os.environ.copy()
    # Claude Code `-p` prefers ANTHROPIC_API_KEY over OAuth subscription.
    for key in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
    ):
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
        return " ".join(unique)
    detail = combined.strip()
    if "usage limit" in detail.lower() or "credit balance" in detail.lower():
        return detail[:600]
    if "Reading additional input from stdin" in detail:
        return "Claude CLI stdin/prompt handling failed."
    return detail[:800] if detail else "unknown error"


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
    # `-p` is required for headless tool loops (Read/Grep/Bash) from a subprocess.
    cmd: list[str] = [
        claude,
        "-p",
        "--output-format",
        "text",
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

    Path(system_path).write_text(system.strip() + "\n", encoding="utf-8")
    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=_timeout_sec(room_turn=room_turn),
            env=_claude_env(),
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
        text = (result.stdout or "").strip()
        if not text:
            raise RuntimeError("claude -p returned empty output")
        return text
    finally:
        Path(system_path).unlink(missing_ok=True)


def model_label() -> str:
    model = os.getenv("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL)
    effort = os.getenv("CLAUDE_REASONING_EFFORT", DEFAULT_CLAUDE_REASONING_EFFORT)
    return f"{model} ({effort})"
