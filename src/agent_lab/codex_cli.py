"""Invoke OpenAI Codex CLI (ChatGPT / Plus auth — not Platform API billing)."""

from __future__ import annotations

import glob
import json
import os
import select
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_lab.agent_models import (  # noqa: E402
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_REASONING_EFFORT,
    DEFAULT_CODEX_ROOM_MAX_COMMANDS,
    DEFAULT_CODEX_ROOM_REASONING_EFFORT,
)
from agent_lab.cli_retry import retry_base_delay_sec, retry_call, retry_max_attempts

_ROOM_TURN_SUFFIX = """\
[Room turn — latency + peer debate]
- This is a **group debate turn**, not a full implementation session: **1–3 short read/grep commands max**, then **you must reply in this turn**.
- After your last command, **write your answer immediately** — do not start another shell command.
- Do **not** ask the Human clarifying questions — decide with Cursor/Claude via working assumptions and `[PROPOSED:]` / ENDORSE / AMEND.
- Long explore loops belong in plan execute (Cursor), not here.
- If sandbox is read-only: verify and propose edits as text/`[PROPOSED:]`; do not attempt file writes.
"""

DEFAULT_CODEX_ROOM_LIMIT_GRACE_SEC = 25


@dataclass
class CodexRunOutcome:
    limit_hit: bool = False
    commands_done: int = 0
    streamed_message: str | None = None


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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
    from agent_lab.agent_preflight import format_codex_exec_error

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
    if detail:
        return format_codex_exec_error(detail[:800])
    return "unknown error"


def _codex_env() -> dict[str, str]:
    from agent_lab.subprocess_env import subprocess_env

    env = subprocess_env()
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


def _reasoning_effort(*, room_turn: bool) -> str:
    if room_turn:
        return os.getenv(
            "CODEX_ROOM_REASONING_EFFORT", DEFAULT_CODEX_ROOM_REASONING_EFFORT
        )
    return os.getenv("CODEX_REASONING_EFFORT", DEFAULT_CODEX_REASONING_EFFORT)


def _optional_timeout_sec(*env_keys: str) -> int | None:
    for key in env_keys:
        raw = (os.getenv(key) or "").strip()
        if raw:
            return int(raw)
    return None


def _timeout_sec(*, room_turn: bool) -> int | None:
    if room_turn:
        return _optional_timeout_sec("CODEX_ROOM_TIMEOUT_SEC", "CODEX_TIMEOUT_SEC")
    return _optional_timeout_sec("CODEX_TIMEOUT_SEC")


def _room_max_commands() -> int:
    return int(os.getenv("CODEX_ROOM_MAX_COMMANDS", str(DEFAULT_CODEX_ROOM_MAX_COMMANDS)))


def _room_limit_grace_sec() -> int:
    return int(
        os.getenv(
            "CODEX_ROOM_LIMIT_GRACE_SEC",
            str(DEFAULT_CODEX_ROOM_LIMIT_GRACE_SEC),
        )
    )


def _sandbox_mode(*, allow_tools: bool, room_turn: bool) -> str:
    if not allow_tools:
        return "read-only"
    if room_turn and not _env_bool("CODEX_ROOM_WORKSPACE_WRITE", False):
        return "read-only"
    return "workspace-write"


def codex_event_label(event: dict[str, Any]) -> str | None:
    """Map Codex `--json` JSONL events to short UI activity lines."""
    typ = event.get("type")
    item = event.get("item") if isinstance(event.get("item"), dict) else {}
    item_type = item.get("type")

    if typ == "turn.started":
        return "Codex turn 시작"
    if typ == "item.started" and item_type == "command_execution":
        cmd = str(item.get("command") or "").strip()
        if len(cmd) > 96:
            cmd = cmd[:93] + "…"
        return f"실행: {cmd}" if cmd else "shell 실행 중"
    if typ == "item.completed" and item_type == "command_execution":
        code = item.get("exit_code")
        if code == 0:
            return "명령 완료"
        return f"명령 exit {code}"
    if typ == "item.completed" and item_type == "agent_message":
        return "답변 정리"
    return None


def _extract_agent_message(item: dict[str, Any]) -> str | None:
    if item.get("type") != "agent_message":
        return None
    for key in ("text", "content", "message"):
        raw = item.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _process_codex_event(
    event: dict[str, Any],
    *,
    on_activity: Callable[[str], None] | None,
    max_commands: int,
    outcome: CodexRunOutcome,
    limit_hit_at: float | None,
) -> float | None:
    """Update outcome from one Codex `--json` event. Returns new limit_hit_at."""
    label = codex_event_label(event)
    if label and on_activity:
        on_activity(label)

    typ = event.get("type")
    item = event.get("item") if isinstance(event.get("item"), dict) else {}
    item_type = item.get("type")

    if typ == "item.completed" and item_type == "agent_message":
        msg = _extract_agent_message(item)
        if msg:
            outcome.streamed_message = msg

    if (
        max_commands
        and typ == "item.completed"
        and item_type == "command_execution"
    ):
        outcome.commands_done += 1
        if outcome.commands_done >= max_commands and not outcome.limit_hit:
            outcome.limit_hit = True
            if on_activity:
                on_activity(
                    f"룸 턴 shell 상한 ({max_commands}회) — 답변 정리 대기"
                )
            return time.monotonic()
    return limit_hit_at


def _should_stop_after_limit(
    outcome: CodexRunOutcome,
    limit_hit_at: float | None,
    *,
    grace_sec: int,
) -> bool:
    if not outcome.limit_hit:
        return False
    if outcome.streamed_message:
        return True
    if limit_hit_at is None:
        return False
    return time.monotonic() - limit_hit_at >= grace_sec


def _build_cmd(
    *,
    codex: str,
    cwd: str,
    out_path: str,
    allow_tools: bool,
    room_turn: bool,
    stream_json: bool,
) -> list[str]:
    cmd: list[str] = [
        codex,
        "exec",
        "--skip-git-repo-check",
        "-C",
        cwd,
        "--sandbox",
        _sandbox_mode(allow_tools=allow_tools, room_turn=room_turn),
        "--dangerously-bypass-approvals-and-sandbox",
        "-o",
        out_path,
    ]
    effort = _reasoning_effort(room_turn=room_turn)
    if effort:
        cmd.extend(["-c", f'model_reasoning_effort="{effort}"'])
    model = os.getenv("CODEX_MODEL", DEFAULT_CODEX_MODEL)
    cmd.extend(["-m", model])
    if stream_json:
        cmd.append("--json")
    cmd.append("-")
    return cmd


def _terminate_proc(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _run_codex(
    cmd: list[str],
    prompt: str,
    *,
    on_activity: Callable[[str], None] | None,
    timeout: int | None,
    room_turn: bool,
) -> CodexRunOutcome:
    env = _codex_env()
    max_commands = _room_max_commands() if room_turn else 0
    grace_sec = _room_limit_grace_sec() if room_turn else 0
    outcome = CodexRunOutcome()

    if not room_turn and on_activity is None:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if result.returncode != 0:
            detail = _format_exec_error(result.stderr or "", result.stdout or "")
            raise RuntimeError(
                f"codex exec failed (exit {result.returncode})"
                + (f": {detail}" if detail else "")
            )
        return outcome

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.stdin is not None
    proc.stdin.write(prompt)
    proc.stdin.close()

    limit_hit_at: float | None = None
    stdout = proc.stdout
    assert stdout is not None

    while True:
        if _should_stop_after_limit(outcome, limit_hit_at, grace_sec=grace_sec):
            if outcome.streamed_message:
                break
            _terminate_proc(proc)
            break

        ready, _, _ = select.select([stdout], [], [], 0.25)
        if not ready:
            if proc.poll() is not None:
                break
            continue

        line = stdout.readline()
        if not line:
            break
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue

        typ = event.get("type")
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        if (
            outcome.limit_hit
            and typ == "item.started"
            and item.get("type") == "command_execution"
        ):
            if on_activity:
                on_activity("shell 상한 초과 — 추가 명령 중단")
            _terminate_proc(proc)
            break

        limit_hit_at = _process_codex_event(
            event,
            on_activity=on_activity,
            max_commands=max_commands,
            outcome=outcome,
            limit_hit_at=limit_hit_at,
        )

    stderr = proc.stderr.read() if proc.stderr is not None else ""
    try:
        if timeout is None:
            proc.wait()
        else:
            proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate_proc(proc)
        effort = _reasoning_effort(room_turn=room_turn)
        raise RuntimeError(
            "Codex exec timed out "
            f"after {timeout}s (room_turn={room_turn}, effort={effort}, "
            f"commands={outcome.commands_done}). "
            "Room turns use read-only sandbox + command cap; "
            "set CODEX_ROOM_WORKSPACE_WRITE=1 only if edits are required."
        ) from exc

    if proc.returncode not in (0, None) and not outcome.limit_hit:
        detail = _format_exec_error(stderr, "")
        raise RuntimeError(
            f"codex exec failed (exit {proc.returncode})"
            + (f": {detail}" if detail else "")
        )
    return outcome


def invoke(
    system: str,
    user: str,
    *,
    permissions: dict | None = None,
    on_activity: Callable[[str], None] | None = None,
    room_turn: bool = False,
) -> str:
    from agent_lab.agent_permissions import codex_cli_allowed
    from agent_lab.workspace_roots import discuss_primary_workspace

    codex = resolve_codex_bin()
    if not codex:
        raise RuntimeError(
            "Codex CLI not found. Install: npm i -g @openai/codex && codex login\n"
            "GUI app: add to .env → CODEX_BIN=/full/path/to/codex "
            "(e.g. ~/.nvm/versions/node/v24.13.1/bin/codex)"
        )

    allow_tools = codex_cli_allowed(permissions)
    discuss = room_turn or bool((permissions or {}).get("_discuss_mode"))
    if discuss and not _env_bool("CODEX_ROOM_WORKSPACE_WRITE", False):
        allow_tools = True  # read-only tools still allowed
    cwd = str(discuss_primary_workspace(permissions))
    out_path = tempfile.mktemp(prefix="agent-lab-codex-", suffix=".txt")

    prompt = f"{system.strip()}\n\n---\n\n{user.strip()}"
    if room_turn:
        prompt = f"{prompt}\n\n{_ROOM_TURN_SUFFIX}"
    if not allow_tools:
        prompt = (
            f"{prompt}\n\n"
            "Do not use tools, MCP, or shell commands. Respond with text only."
        )

    stream_json = room_turn or on_activity is not None
    cmd = _build_cmd(
        codex=codex,
        cwd=cwd,
        out_path=out_path,
        allow_tools=allow_tools,
        room_turn=room_turn,
        stream_json=stream_json,
    )
    timeout = _timeout_sec(room_turn=room_turn)
    max_commands = _room_max_commands() if room_turn else 0

    def _run_once() -> str:
        Path(out_path).unlink(missing_ok=True)
        outcome = _run_codex(
            cmd,
            prompt,
            on_activity=on_activity,
            timeout=timeout,
            room_turn=room_turn,
        )
        text = Path(out_path).read_text(encoding="utf-8").strip()
        if text:
            return text
        if outcome.streamed_message:
            return outcome.streamed_message
        if outcome.limit_hit:
            return (
                f"[Codex room turn stopped after {max_commands} shell command(s) — "
                "no final message; narrow scope or retry.]"
            )
        raise RuntimeError("codex exec returned empty output")

    def _on_retry(attempt: int, max_attempts: int, _reason: str) -> None:
        if on_activity:
            on_activity(f"재시도 {attempt}/{max_attempts} — Codex CLI 일시 오류")

    try:
        return retry_call(
            _run_once,
            max_attempts=retry_max_attempts(room_turn=room_turn),
            base_delay_sec=retry_base_delay_sec(),
            on_retry_label=_on_retry,
        )
    finally:
        Path(out_path).unlink(missing_ok=True)


def model_label() -> str:
    model = os.getenv("CODEX_MODEL", DEFAULT_CODEX_MODEL)
    effort = os.getenv("CODEX_REASONING_EFFORT", DEFAULT_CODEX_REASONING_EFFORT)
    room = os.getenv("CODEX_ROOM_REASONING_EFFORT", DEFAULT_CODEX_ROOM_REASONING_EFFORT)
    return f"{model} (room:{room}, default:{effort})"
