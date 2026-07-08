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

from agent_lab.agent.permissions import codex_cli_allowed
from agent_lab.agent.models import (  # noqa: E402
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_REASONING_EFFORT,
    DEFAULT_CODEX_ROOM_IDLE_TIMEOUT_SEC,
    DEFAULT_CODEX_ROOM_MAX_COMMANDS,
    DEFAULT_CODEX_ROOM_REASONING_EFFORT,
    DEFAULT_CODEX_ROOM_TIMEOUT_SEC,
)
from agent_lab.cli_retry import retry_base_delay_sec, retry_call, retry_max_attempts
from agent_lab.env_flags import env_bool, optional_env_int

_ROOM_TURN_SUFFIX = """\
[Room turn — latency + peer debate]
- This is a **group debate turn**, not a full implementation session: **1–3 short read/grep commands max**, then **you must reply in this turn**.
- After your last command, **write your answer immediately** — do not start another shell command.
- Decide with Cursor/Claude via working assumptions and `[PROPOSED:]` / ENDORSE / AMEND.
- Long explore loops belong in plan execute (Cursor), not here.
- If sandbox is read-only: verify and propose edits as text/`[PROPOSED:]`; do not attempt file writes.
"""

DEFAULT_CODEX_ROOM_LIMIT_GRACE_SEC = 25
DEFAULT_CODEX_ROOM_HEARTBEAT_SEC = 15


@dataclass
class CodexRunOutcome:
    limit_hit: bool = False
    commands_done: int = 0
    streamed_message: str | None = None
    json_events: int = 0
    stderr: str = ""
    # True once Codex emits its first response item (reasoning/message/command).
    # The wall-clock cap only guards time-to-first-output; once a turn is actively
    # responding it runs uncapped (idle timeout still guards mid-response stalls).
    response_started: bool = False


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
    for bin_path in nvm_matches:
        if Path(bin_path).is_file():
            return bin_path

    for path_candidate in (
        home / ".local/bin/codex",
        Path("/opt/homebrew/bin/codex"),
        Path("/usr/local/bin/codex"),
    ):
        if path_candidate.is_file():
            return str(path_candidate)

    return None


def is_available() -> bool:
    return resolve_codex_bin() is not None


def _format_exec_error(stderr: str, stdout: str) -> str:
    """Surface Codex ERROR lines; stderr often includes a long session banner first."""
    from agent_lab.agent.preflight import format_codex_exec_error

    combined = f"{stderr or ''}\n{stdout or ''}"
    errors = [ln.strip() for ln in combined.splitlines() if ln.strip().startswith("ERROR:")]
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
    low = detail.lower()
    if "401" in detail or "token_invalidated" in low or "authentication token has been invalidated" in low:
        from agent_lab.codex.oauth import codex_auth_failure_remediation

        hint = codex_auth_failure_remediation(detail)[0]
        return f"{format_codex_exec_error(detail[:600])} — {hint}"
    if "Reading additional input from stdin" in detail:
        return "Codex CLI stdin/prompt handling failed. Update Agent Lab (prompt is passed on stdin, not as a CLI arg)."
    if detail:
        return format_codex_exec_error(detail[:800])
    return "Codex CLI exited without stderr output. Re-run `codex login` or re-capture OAuth in Settings (메인/서브)."


def _codex_env(*, api_key: str | None = None) -> dict[str, str]:
    from agent_lab.subprocess_env import subprocess_env

    env = subprocess_env()
    if api_key and api_key.strip():
        env["OPENAI_API_KEY"] = api_key.strip()
    else:
        env.pop("OPENAI_API_KEY", None)
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
        return os.getenv("CODEX_ROOM_REASONING_EFFORT", DEFAULT_CODEX_ROOM_REASONING_EFFORT)
    return os.getenv("CODEX_REASONING_EFFORT", DEFAULT_CODEX_REASONING_EFFORT)


def _timeout_sec(*, room_turn: bool) -> int | None:
    if room_turn:
        override = optional_env_int("CODEX_ROOM_TIMEOUT_SEC", "CODEX_TIMEOUT_SEC")
        if override is not None:
            return override if override > 0 else None
        return DEFAULT_CODEX_ROOM_TIMEOUT_SEC
    return optional_env_int("CODEX_TIMEOUT_SEC")


def _idle_timeout_sec(*, room_turn: bool) -> int | None:
    if not room_turn:
        return None
    raw = (os.getenv("CODEX_ROOM_IDLE_TIMEOUT_SEC") or "").strip()
    if raw:
        val = int(raw)
        return val if val > 0 else None
    return DEFAULT_CODEX_ROOM_IDLE_TIMEOUT_SEC


def _room_heartbeat_sec() -> int:
    raw = (os.getenv("CODEX_ROOM_HEARTBEAT_SEC") or "").strip()
    if raw:
        return max(15, int(raw))
    return DEFAULT_CODEX_ROOM_HEARTBEAT_SEC


def _stderr_tail(text: str, *, limit: int = 1200) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    return "…" + cleaned[-limit:]


def _persist_codex_stderr(text: str) -> str | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    path = Path(tempfile.mktemp(prefix="agent-lab-codex-stderr-", suffix=".log"))
    path.write_text(cleaned, encoding="utf-8")
    return str(path)


# Decisive (non-transient) auth failure markers from the codex CLI's own
# login manager. Deliberately narrow: a bare "401" is NOT enough — the same
# stderr stream carries 401s from unrelated MCP servers (e.g. Linear) that
# must not kill the turn. A revoked/invalidated refresh token never recovers
# by retrying, so the first sighting is grounds to abort immediately instead
# of letting the CLI spin until the idle timeout.
_CODEX_AUTH_REVOKED_MARKERS = (
    "refresh_token_invalidated",
    "refresh token was revoked",
    "authentication token has been invalidated",
    "please log out and sign in again",
)


def is_codex_auth_revoked_output(text: str) -> bool:
    """True when codex CLI output shows a dead OAuth session (re-login required)."""
    low = text.lower()
    return any(marker in low for marker in _CODEX_AUTH_REVOKED_MARKERS)


def _format_codex_stall_error(
    *,
    reason: str,
    room_turn: bool,
    outcome: CodexRunOutcome,
    idle_sec: int | None = None,
    wall_sec: int | None = None,
    stderr_path: str | None = None,
) -> str:
    parts = [
        reason,
        f"room_turn={room_turn}",
        f"json_events={outcome.json_events}",
        f"commands={outcome.commands_done}",
    ]
    if idle_sec is not None:
        parts.append(f"idle_sec={idle_sec}")
    if wall_sec is not None:
        parts.append(f"wall_sec={wall_sec}")
    tail = _stderr_tail(outcome.stderr)
    if tail:
        parts.append(f"stderr_tail={tail!r}")
    if stderr_path:
        parts.append(f"stderr_log={stderr_path}")
    parts.append("Tune CODEX_ROOM_IDLE_TIMEOUT_SEC / CODEX_ROOM_TIMEOUT_SEC or inspect stderr_log.")
    return "Codex exec stalled — " + ", ".join(parts)


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
    if room_turn and not env_bool("CODEX_ROOM_WORKSPACE_WRITE", False):
        return "read-only"
    return "workspace-write"


def _codex_item_type(item: dict[str, Any]) -> str:
    raw = item.get("type") or item.get("item_type") or ""
    return str(raw).strip()


def _codex_mcp_tool_label(item: dict[str, Any], *, started: bool) -> str | None:
    tool = str(item.get("tool") or "").strip()
    server = str(item.get("server") or "").strip()
    if started:
        if tool == "ask_human":
            return "Human Inbox: question"
        if tool == "propose_build":
            return "Human Inbox: build proposal"
        if tool:
            return f"MCP: {server}/{tool}" if server else f"MCP: {tool}"
        return "MCP tool"
    status = str(item.get("status") or "").strip().lower()
    if status == "failed":
        err = item.get("error")
        msg = ""
        if isinstance(err, dict):
            msg = str(err.get("message") or "").strip()
        return f"MCP failed: {msg}" if msg else "MCP tool failed"
    if tool == "ask_human":
        return "Human Inbox: answered"
    if tool == "propose_build":
        return "Human Inbox: GO decision"
    if tool:
        return f"MCP done: {tool}"
    return "MCP tool done"


def codex_event_label(event: dict[str, Any]) -> str | None:
    """Map Codex `--json` JSONL events to short UI activity lines."""
    typ = event.get("type")
    item_raw = event.get("item")
    item: dict[str, Any] = item_raw if isinstance(item_raw, dict) else {}
    item_type = _codex_item_type(item)

    if typ == "turn.started":
        return "Codex turn 시작"
    if typ in ("item.started", "item.completed") and item_type == "mcp_tool_call":
        return _codex_mcp_tool_label(item, started=typ == "item.started")
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
    on_bridge_event: Callable[[str, dict[str, Any]], None] | None = None,
    max_commands: int,
    outcome: CodexRunOutcome,
    limit_hit_at: float | None,
) -> float | None:
    """Update outcome from one Codex `--json` event. Returns new limit_hit_at."""
    if on_bridge_event:
        from agent_lab.agent.stream_parser import parse_codex_json_event

        for kind, data in parse_codex_json_event(event):
            on_bridge_event(kind, data)

    label = codex_event_label(event)
    if label and on_activity:
        on_activity(label)

    typ = event.get("type")
    item_raw = event.get("item")
    item: dict[str, Any] = item_raw if isinstance(item_raw, dict) else {}
    item_type = item.get("type")

    # Any response item (reasoning / message / command) means the turn has begun
    # producing output — as opposed to session metadata or stderr retry noise.
    if isinstance(typ, str) and typ.startswith("item."):
        outcome.response_started = True

    if typ == "item.completed" and item_type == "agent_message":
        msg = _extract_agent_message(item)
        if msg:
            outcome.streamed_message = msg

    if max_commands and typ == "item.completed" and item_type == "command_execution":
        outcome.commands_done += 1
        if outcome.commands_done >= max_commands and not outcome.limit_hit:
            outcome.limit_hit = True
            if on_activity:
                on_activity(f"룸 턴 shell 상한 ({max_commands}회) — 답변 정리 대기")
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
    config_overrides: list[str] | None = None,
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
    if config_overrides:
        cmd.extend(config_overrides)
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
    on_bridge_event: Callable[[str, dict[str, Any]], None] | None = None,
    timeout: int | None,
    room_turn: bool,
    api_key: str | None = None,
) -> CodexRunOutcome:
    env = _codex_env(api_key=api_key)
    max_commands = _room_max_commands() if room_turn else 0
    grace_sec = _room_limit_grace_sec() if room_turn else 0
    idle_timeout = _idle_timeout_sec(room_turn=room_turn)
    heartbeat_sec = _room_heartbeat_sec() if room_turn else 0
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
            combined = f"{result.stderr or ''}\n{result.stdout or ''}"
            if is_codex_auth_revoked_output(combined):
                from agent_lab.codex.oauth import mark_codex_auth_revoked

                mark_codex_auth_revoked("codex exec exited on revoked OAuth refresh token")
            detail = _format_exec_error(result.stderr or "", result.stdout or "")
            raise RuntimeError(f"codex exec failed (exit {result.returncode})" + (f": {detail}" if detail else ""))
        return outcome

    from agent_lab.run.control import (
        RoomRunCancelled,
        is_cancelled,
        register_child_process,
        unregister_child_process,
    )

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    register_child_process(proc)
    if on_activity and room_turn:
        on_activity("Codex CLI 실행 중…")
    assert proc.stdin is not None
    proc.stdin.write(prompt)
    proc.stdin.close()

    limit_hit_at: float | None = None
    stdout = proc.stdout
    stderr = proc.stderr
    assert stdout is not None
    assert stderr is not None

    started_at = time.monotonic()
    last_activity_at = started_at
    last_heartbeat_at = started_at
    stderr_parts: list[str] = []

    def _touch_activity() -> None:
        nonlocal last_activity_at
        last_activity_at = time.monotonic()

    def _record_stderr(chunk: str) -> None:
        if not chunk:
            return
        stderr_parts.append(chunk)
        _touch_activity()
        if is_codex_auth_revoked_output(chunk):
            _raise_auth_revoked()
        line = chunk.strip().splitlines()[0] if chunk.strip() else ""
        if line and on_activity and len(line) <= 160:
            on_activity(f"Codex stderr: {line[:160]}")

    def _raise_auth_revoked() -> None:
        outcome.stderr = "".join(stderr_parts)
        stderr_path = _persist_codex_stderr(outcome.stderr)
        _terminate_proc(proc)
        from agent_lab.codex.oauth import (
            codex_auth_failure_remediation,
            mark_codex_auth_revoked,
        )

        hint = codex_auth_failure_remediation("refresh token revoked")[0]
        mark_codex_auth_revoked(
            "codex exec died on revoked OAuth refresh token" + (f" (stderr_log={stderr_path})" if stderr_path else "")
        )
        if on_activity:
            on_activity("Codex OAuth 세션 만료 — 즉시 중단 (재로그인 필요)")
        msg = f"codex exec failed (auth): OAuth refresh token revoked — {hint}"
        if stderr_path:
            msg += f" (stderr_log={stderr_path})"
        raise RuntimeError(msg)

    def _raise_stall(
        reason: str,
        *,
        idle_sec: int | None = None,
        cause: BaseException | None = None,
    ) -> None:
        outcome.stderr = "".join(stderr_parts)
        stderr_path = _persist_codex_stderr(outcome.stderr)
        wall_sec = int(time.monotonic() - started_at)
        _terminate_proc(proc)
        err = RuntimeError(
            _format_codex_stall_error(
                reason=reason,
                room_turn=room_turn,
                outcome=outcome,
                idle_sec=idle_sec,
                wall_sec=wall_sec,
                stderr_path=stderr_path,
            )
        )
        # Decisive, not transient: the process was killed after genuinely
        # stalling. The message text may contain "timeout" (matches the
        # retryable-pattern regex) even though retrying just repeats the same
        # multi-minute wait — mark it explicitly so retry_call doesn't guess.
        err.agent_lab_retryable = False  # type: ignore[attr-defined]
        if cause is not None:
            raise err from cause
        raise err

    try:
        while True:
            if is_cancelled():
                _terminate_proc(proc)
                raise RoomRunCancelled("run cancelled by user")

            now = time.monotonic()
            # Wall-clock cap guards only time-to-first-output: an agent stuck on a
            # usage/rate limit (retrying via stderr, never emitting a response item)
            # is bounded, while a turn that is actively responding runs uncapped.
            if timeout is not None and not outcome.response_started and now - started_at >= timeout:
                _raise_stall(
                    f"no response started within {timeout}s",
                    idle_sec=int(now - last_activity_at),
                )
            if idle_timeout is not None and now - last_activity_at >= idle_timeout:
                _raise_stall(
                    f"no JSONL/stderr activity for {idle_timeout}s",
                    idle_sec=idle_timeout,
                )
            if on_activity and heartbeat_sec and room_turn and now - last_heartbeat_at >= heartbeat_sec:
                idle_for = int(now - last_activity_at)
                on_activity(f"Codex 대기 중… ({idle_for}s, events={outcome.json_events})")
                last_heartbeat_at = now
            elif (
                on_activity
                and room_turn
                and not outcome.response_started
                and now - started_at >= 8
                and last_heartbeat_at == started_at
            ):
                idle_for = int(now - last_activity_at)
                on_activity(f"Codex 응답 대기… ({idle_for}s, events={outcome.json_events})")
                last_heartbeat_at = now

            if _should_stop_after_limit(outcome, limit_hit_at, grace_sec=grace_sec):
                if outcome.streamed_message:
                    break
                _terminate_proc(proc)
                break

            exited = proc.poll()
            if exited is not None and outcome.streamed_message:
                break

            watch = [stdout, stderr]
            ready, _, _ = select.select(watch, [], [], 0.25)
            if not ready:
                if proc.poll() is not None:
                    break
                continue

            for fd in ready:
                if fd is stderr:
                    # os.read returns whatever is available; TextIOWrapper's
                    # .read(4096) would block until 4096 chars or EOF, freezing
                    # the whole watch loop (and its idle-timeout / fail-fast
                    # checks) on a process that trickles stderr then hangs.
                    raw = os.read(stderr.fileno(), 4096)
                    if raw:
                        _record_stderr(raw.decode("utf-8", "replace"))
                    continue

                line = stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        break
                    continue
                stripped = line.strip()
                if not stripped:
                    continue
                _touch_activity()
                try:
                    event = json.loads(stripped)
                except json.JSONDecodeError:
                    continue

                outcome.json_events += 1
                typ = event.get("type")
                item = event.get("item") if isinstance(event.get("item"), dict) else {}
                if outcome.limit_hit and typ == "item.started" and item.get("type") == "command_execution":
                    if on_activity:
                        on_activity("shell 상한 초과 — 추가 명령 중단")
                    _terminate_proc(proc)
                    break

                limit_hit_at = _process_codex_event(
                    event,
                    on_activity=on_activity,
                    on_bridge_event=on_bridge_event,
                    max_commands=max_commands,
                    outcome=outcome,
                    limit_hit_at=limit_hit_at,
                )
            if proc.poll() is not None and not select.select([stdout], [], [], 0)[0]:
                break
    finally:
        unregister_child_process(proc)

    remainder = stderr.read()
    if remainder:
        stderr_parts.append(remainder)
    outcome.stderr = "".join(stderr_parts)

    try:
        if timeout is None:
            proc.wait()
        else:
            remaining = timeout - (time.monotonic() - started_at)
            if remaining <= 0:
                _raise_stall(
                    f"wall-clock timeout after {timeout}s",
                    idle_sec=int(time.monotonic() - last_activity_at),
                )
            proc.wait(timeout=remaining)
    except subprocess.TimeoutExpired as exc:
        _raise_stall(
            f"wall-clock timeout after {timeout}s",
            idle_sec=int(time.monotonic() - last_activity_at),
            cause=exc,
        )

    if proc.returncode not in (0, None) and not outcome.limit_hit:
        if is_cancelled():
            raise RoomRunCancelled("run cancelled by user")
        if is_codex_auth_revoked_output(outcome.stderr):
            from agent_lab.codex.oauth import mark_codex_auth_revoked

            mark_codex_auth_revoked("codex exec exited on revoked OAuth refresh token")
        detail = _format_exec_error(
            outcome.stderr,
            outcome.streamed_message or "",
        )
        stderr_path = _persist_codex_stderr(outcome.stderr)
        msg = f"codex exec failed (exit {proc.returncode})"
        if detail:
            msg += f": {detail}"
        if stderr_path:
            msg += f" (stderr_log={stderr_path})"
        raise RuntimeError(msg)
    return outcome


def invoke(
    system: str,
    user: str,
    *,
    permissions: dict | None = None,
    on_activity: Callable[[str], None] | None = None,
    on_bridge_event: Callable[[str, dict[str, Any]], None] | None = None,
    room_turn: bool = False,
    session_folder: str | Path | None = None,
    inbox_mcp: bool = False,
    request_structured_envelope: bool = False,
) -> str:
    from agent_lab.workspace.roots import discuss_primary_workspace

    execute_plugins = bool((permissions or {}).get("_execute_plugins"))
    use_inbox_mcp = False
    if inbox_mcp and session_folder is not None:
        from agent_lab.cursor.inbox_mcp import mount_inbox_mcp_when_requested

        use_inbox_mcp = mount_inbox_mcp_when_requested(inbox_mcp)

    from agent_lab.runtime.adapters.codex import can_route_codex_proxy, invoke_codex_proxy

    if can_route_codex_proxy(inbox_mcp=use_inbox_mcp, execute_plugins=execute_plugins):
        proxy_user = user.strip()
        if room_turn:
            proxy_user = f"{proxy_user}\n\n{_ROOM_TURN_SUFFIX}"
        if request_structured_envelope:
            from agent_lab.structured_envelope_adapter import structured_envelope_system_addon

            proxy_user = f"{proxy_user}\n\n{structured_envelope_system_addon(compact=True)}"
        return invoke_codex_proxy(
            system,
            proxy_user,
            room_turn=room_turn,
            on_activity=on_activity,
            on_bridge_event=on_bridge_event,
        )

    codex = resolve_codex_bin()
    if not codex:
        raise RuntimeError(
            "Codex CLI not found. Install: npm i -g @openai/codex && codex login\n"
            "GUI app: add to .env → CODEX_BIN=/full/path/to/codex "
            "(e.g. ~/.nvm/versions/node/v24.13.1/bin/codex)"
        )

    config_overrides: list[str] | None = None
    if use_inbox_mcp and session_folder is not None:
        from agent_lab.cursor.inbox_mcp import (
            build_codex_inbox_mcp_config_args,
            inbox_mcp_build_kwargs,
        )

        config_overrides = build_codex_inbox_mcp_config_args(
            Path(session_folder),
            **inbox_mcp_build_kwargs(permissions),
        )
    if session_folder is not None:
        from agent_lab.cursor.session_metrics_mcp import (
            build_codex_session_metrics_config_args,
            session_metrics_mcp_enabled,
        )

        if session_metrics_mcp_enabled():
            metrics_args = build_codex_session_metrics_config_args(Path(session_folder))
            config_overrides = (config_overrides or []) + metrics_args
    if execute_plugins and session_folder is not None:
        from agent_lab.session.plugin_runtime import merge_codex_execute_config_overrides

        config_overrides = merge_codex_execute_config_overrides(
            Path(session_folder),
            config_overrides,
        )

    allow_tools = codex_cli_allowed(permissions) or use_inbox_mcp or execute_plugins
    discuss = room_turn or bool((permissions or {}).get("_discuss_mode"))
    if discuss and not env_bool("CODEX_ROOM_WORKSPACE_WRITE", False):
        allow_tools = True  # read-only tools still allowed
    cwd = str(discuss_primary_workspace(permissions))
    out_path = tempfile.mktemp(prefix="agent-lab-codex-", suffix=".txt")

    prompt = f"{system.strip()}\n\n---\n\n{user.strip()}"
    if request_structured_envelope:
        from agent_lab.structured_envelope_adapter import structured_envelope_system_addon

        prompt = f"{prompt}\n\n{structured_envelope_system_addon(compact=True)}"
    if room_turn:
        prompt = f"{prompt}\n\n{_ROOM_TURN_SUFFIX}"
    if not allow_tools:
        prompt = f"{prompt}\n\nDo not use tools, MCP, or shell commands. Respond with text only."

    stream_json = room_turn or on_activity is not None or on_bridge_event is not None or use_inbox_mcp
    cmd = _build_cmd(
        codex=codex,
        cwd=cwd,
        out_path=out_path,
        allow_tools=allow_tools,
        room_turn=room_turn,
        stream_json=stream_json,
        config_overrides=config_overrides,
    )
    timeout = _timeout_sec(room_turn=room_turn)
    max_commands = _room_max_commands() if room_turn else 0

    def _run_once(api_key: str | None) -> str:
        Path(out_path).unlink(missing_ok=True)
        outcome = _run_codex(
            cmd,
            prompt,
            on_activity=on_activity,
            on_bridge_event=on_bridge_event,
            timeout=timeout,
            room_turn=room_turn,
            api_key=api_key,
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
        from agent_lab.agent.hooks_materializer import native_agent_hooks_overlay
        from agent_lab.codex.oauth import call_with_codex_oauth_fallback

        def _run_for_oauth_slot(_slot: object) -> str:
            def _run_with_hooks() -> str:
                with native_agent_hooks_overlay("codex", session_folder, cwd):
                    return _run_once(None)

            return retry_call(
                _run_with_hooks,
                max_attempts=retry_max_attempts(room_turn=room_turn),
                base_delay_sec=retry_base_delay_sec(),
                on_retry_label=_on_retry,
            )

        def _on_oauth_switch(label: str, _slot: object) -> None:
            if on_activity:
                on_activity(f"Codex OAuth → {label} 계정")

        return call_with_codex_oauth_fallback(
            _run_for_oauth_slot,
            on_switch=_on_oauth_switch,
        )
    finally:
        Path(out_path).unlink(missing_ok=True)


def model_label() -> str:
    model = os.getenv("CODEX_MODEL", DEFAULT_CODEX_MODEL)
    effort = os.getenv("CODEX_REASONING_EFFORT", DEFAULT_CODEX_REASONING_EFFORT)
    room = os.getenv("CODEX_ROOM_REASONING_EFFORT", DEFAULT_CODEX_ROOM_REASONING_EFFORT)
    return f"{model} (room:{room}, default:{effort})"
