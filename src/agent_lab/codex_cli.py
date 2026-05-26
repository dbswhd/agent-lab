"""Invoke OpenAI Codex CLI (ChatGPT / Plus auth — not Platform API billing)."""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


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


def invoke(system: str, user: str) -> str:
    codex = resolve_codex_bin()
    if not codex:
        raise RuntimeError(
            "Codex CLI not found. Install: npm i -g @openai/codex && codex login\n"
            "GUI app: add to .env → CODEX_BIN=/full/path/to/codex "
            "(e.g. ~/.nvm/versions/node/v24.13.1/bin/codex)"
        )

    cwd = os.getenv("CODEX_CWD", str(PROJECT_ROOT))
    out_path = tempfile.mktemp(prefix="agent-lab-codex-", suffix=".txt")

    prompt = (
        f"{system.strip()}\n\n---\n\n{user.strip()}\n\n"
        "Do not use tools, MCP, or shell commands. Respond with text only."
    )

    cmd: list[str] = [
        codex,
        "exec",
        "--skip-git-repo-check",
        "-C",
        cwd,
        "--sandbox",
        "read-only",
        "--dangerously-bypass-approvals-and-sandbox",
        "-o",
        out_path,
    ]

    if effort := os.getenv("CODEX_REASONING_EFFORT", "low"):
        cmd.extend(["-c", f'model_reasoning_effort="{effort}"'])
    if model := os.getenv("CODEX_MODEL"):
        cmd.extend(["-m", model])

    cmd.append(prompt)

    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("CODEX_TIMEOUT_SEC", "300")),
            env=_codex_env(),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(
                f"codex exec failed (exit {result.returncode})"
                + (f": {detail[:500]}" if detail else "")
            )
        text = Path(out_path).read_text(encoding="utf-8").strip()
        if not text:
            raise RuntimeError("codex exec returned empty output")
        return text
    finally:
        Path(out_path).unlink(missing_ok=True)


def model_label() -> str:
    return os.getenv("CODEX_MODEL") or "codex/chatgpt (gpt-5.5 default)"
