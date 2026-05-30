"""Invoke OpenAI Codex CLI (ChatGPT / Plus auth — not Platform API billing)."""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from agent_lab.agent_models import (  # noqa: E402
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_REASONING_EFFORT,
)


def resolve_codex_bin() -> str | None:
    """Find codex binary (GUI apps often lack nvm on PATH)."""
    explicit = (os.getenv("CODEX_BIN") or "").strip()
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return str(p.resolve())

    found = shutil.which("codex")
    if found:
        return found

    home = Path.home()
    nvm_glob = str(home / ".nvm/versions/node/*/bin/codex")
    nvm_matches = sorted(glob.glob(nvm_glob), reverse=True)
    for candidate in nvm_matches:
        if Path(candidate).is_file():
            return candidate

    for candidate in (
        home / ".local/bin/codex",
        Path("/opt/homebrew/bin/codex"),
        Path("/usr/local/bin/codex"),
    ):
        if candidate.is_file():
            return str(candidate)

    return None


def is_available() -> bool:
    return resolve_codex_bin() is not None


def _format_exec_error(stderr: str, stdout: str) -> str:
    """Surface Codex ERROR lines; stderr often includes a long session banner first."""
    combined = f"{stderr or ''}\n{stdout or ''}"
    errors = [
        ln.strip()
        for ln in combined.splitlines()
        if ln.strip().startswith("ERROR:")
    ]
    if errors:
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for e in errors:
            if e not in seen:
                seen.add(e)
                unique.append(e)
        return " ".join(unique)
    detail = combined.strip()
    if "usage limit" in detail.lower():
        return (
            "Codex usage limit reached (ChatGPT/Codex subscription). "
            "Try again later or upgrade — see chatgpt.com/explore/plus"
        )
    if "Reading additional input from stdin" in detail:
        return (
            "Codex CLI stdin/prompt handling failed. "
            "Update Agent Lab (prompt is passed on stdin, not as a CLI arg)."
        )
    return detail[:800] if detail else "unknown error"


def _codex_env() -> dict[str, str]:
    env = os.environ.copy()
    codex = resolve_codex_bin()
    if codex:
        bin_dir = str(Path(codex).parent)
        path = env.get("PATH", "")
        parts = [p for p in path.split(":") if p]
        if bin_dir not in parts:
            env["PATH"] = f"{bin_dir}:{path}" if path else bin_dir
    env.setdefault("HOME", str(Path.home()))
    env.setdefault("TERM", "xterm-256color")
    env.pop("NO_COLOR", None)
    return env


def invoke(system: str, user: str, *, permissions: dict | None = None) -> str:
    from agent_lab.agent_permissions import codex_cli_allowed
    from agent_lab.workspace_roots import primary_workspace

    codex = resolve_codex_bin()
    if not codex:
        raise RuntimeError(
            "Codex CLI not found. Install: npm i -g @openai/codex && codex login\n"
            "GUI app: add to .env → CODEX_BIN=/full/path/to/codex "
            "(e.g. ~/.nvm/versions/node/v24.13.1/bin/codex)"
        )

    allow_tools = codex_cli_allowed(permissions)
    cwd = str(primary_workspace(permissions))
    out_path = tempfile.mktemp(prefix="agent-lab-codex-", suffix=".txt")

    prompt = f"{system.strip()}\n\n---\n\n{user.strip()}"
    if not allow_tools:
        prompt = (
            f"{prompt}\n\n"
            "Do not use tools, MCP, or shell commands. Respond with text only."
        )

    cmd: list[str] = [
        codex,
        "exec",
        "--skip-git-repo-check",
        "-C",
        cwd,
        "--sandbox",
        "workspace-write" if allow_tools else "read-only",
        "--dangerously-bypass-approvals-and-sandbox",
        "-o",
        out_path,
    ]

    if effort := os.getenv("CODEX_REASONING_EFFORT", DEFAULT_CODEX_REASONING_EFFORT):
        cmd.extend(["-c", f'model_reasoning_effort="{effort}"'])
    model = os.getenv("CODEX_MODEL", DEFAULT_CODEX_MODEL)
    cmd.extend(["-m", model])

    # Prompt on stdin (`-`). CLI arg + closed stdin makes Codex print
    # "Reading additional input from stdin..." and exit 1; long threads also risk ARG_MAX.
    cmd.append("-")

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("CODEX_TIMEOUT_SEC", "300")),
            env=_codex_env(),
        )
        if result.returncode != 0:
            detail = _format_exec_error(result.stderr or "", result.stdout or "")
            raise RuntimeError(
                f"codex exec failed (exit {result.returncode})"
                + (f": {detail}" if detail else "")
            )
        text = Path(out_path).read_text(encoding="utf-8").strip()
        if not text:
            raise RuntimeError("codex exec returned empty output")
        return text
    finally:
        Path(out_path).unlink(missing_ok=True)


def model_label() -> str:
    model = os.getenv("CODEX_MODEL", DEFAULT_CODEX_MODEL)
    effort = os.getenv("CODEX_REASONING_EFFORT", DEFAULT_CODEX_REASONING_EFFORT)
    return f"{model} ({effort})"
