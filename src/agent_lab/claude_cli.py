"""Invoke Claude Code CLI (subscription / OAuth — not Platform API by default)."""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

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
    home = Path.home()
    roots: list[Path] = []
    block = (permissions or {}).get("claude") or {}
    if block.get("local_agent_lab"):
        roots.append(_project_root())
    if block.get("local_pipeline"):
        pipeline = Path(
            os.getenv("QUANT_PIPELINE_ROOT", str(home / "Projects" / "quant-pipeline"))
        ).expanduser()
        if pipeline.is_dir():
            roots.append(pipeline.resolve())
    if (block.get("tools") or block.get("write")) and not roots:
        roots.append(_project_root())
    return roots


def _claude_env() -> dict[str, str]:
    env = os.environ.copy()
    # Claude Code `-p` prefers ANTHROPIC_API_KEY over OAuth subscription.
    # Agent Lab loads .env for classic graph (langchain API); room Claude uses CLI subscription.
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


def invoke(system: str, user: str, *, permissions: dict | None = None) -> str:
    from agent_lab.agent_permissions import claude_tools_allowed, claude_write_allowed

    claude = resolve_claude_bin()
    if not claude:
        raise RuntimeError(
            "Claude Code CLI not found. Install: npm i -g @anthropic-ai/claude-code "
            "&& claude login\n"
            "GUI app: add to .env → CLAUDE_BIN=/full/path/to/claude "
            "(e.g. ~/.nvm/versions/node/v24.13.1/bin/claude)"
        )

    allow_read = claude_tools_allowed(permissions)
    allow_write = claude_write_allowed(permissions)
    cwd = os.getenv("CLAUDE_CWD", str(_project_root()))

    system_path = tempfile.mktemp(prefix="agent-lab-claude-sys-", suffix=".txt")
    cmd: list[str] = [
        claude,
        "-p",
        "--no-session-persistence",
        "--output-format",
        "text",
        "--exclude-dynamic-system-prompt-sections",
        "--system-prompt-file",
        system_path,
    ]

    if allow_write:
        cmd.extend(["--permission-mode", "acceptEdits"])
    else:
        cmd.extend(["--permission-mode", "plan"])

    for root in resolve_claude_roots(permissions):
        cmd.extend(["--add-dir", str(root)])

    if model := os.getenv("CLAUDE_MODEL"):
        cmd.extend(["--model", model])
    if effort := os.getenv("CLAUDE_REASONING_EFFORT"):
        cmd.extend(["--effort", effort])

    prompt = user.strip()
    if not allow_read and not allow_write:
        prompt = (
            f"{prompt}\n\n"
            "Do not use tools, MCP, or shell commands. Respond with text only."
        )

    cmd.append(prompt)

    Path(system_path).write_text(system.strip() + "\n", encoding="utf-8")
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("CLAUDE_TIMEOUT_SEC", "300")),
            env=_claude_env(),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            if "credit balance is too low" in detail.lower():
                detail = (
                    f"{detail} "
                    "(Agent Lab strips ANTHROPIC_API_KEY for Claude Code CLI; "
                    "if this persists run: claude logout && claude login)"
                )
            raise RuntimeError(
                f"claude -p failed (exit {result.returncode})"
                + (f": {detail[:500]}" if detail else "")
            )
        text = (result.stdout or "").strip()
        if not text:
            raise RuntimeError("claude -p returned empty output")
        return text
    finally:
        Path(system_path).unlink(missing_ok=True)


def model_label() -> str:
    return os.getenv("CLAUDE_MODEL") or "claude-code (subscription default)"
