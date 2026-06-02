"""Server-side room hooks (TaskCompleted, TeammateIdle) — not per-process .claude hooks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    tomllib = None  # type: ignore[assignment,misc]

HOOK_EXIT_BLOCK = 2
DEFAULT_HOOK_TIMEOUT_S = 30


@dataclass
class HookResult:
    blocked: bool
    feedback: str
    exit_code: int
    event: str
    command: str = ""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def hooks_config_paths() -> list[Path]:
    paths: list[Path] = []
    env = os.getenv("AGENT_LAB_HOOKS_PATH", "").strip()
    if env:
        paths.append(Path(env).expanduser())
    paths.append(_repo_root() / ".agent-lab" / "hooks.toml")
    from agent_lab.app_config import config_dir

    paths.append(config_dir() / "hooks.toml")
    return paths


def load_hooks_config() -> dict[str, Any]:
    if tomllib is None:
        return {}
    for path in hooks_config_paths():
        if path.is_file():
            try:
                data = tomllib.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
            except (OSError, ValueError):
                continue
    return {}


def _commands_for_event(cfg: dict[str, Any], event: str) -> list[str]:
    hooks = cfg.get("hooks")
    if not isinstance(hooks, dict):
        return []
    raw = hooks.get(event)
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if isinstance(raw, list):
        out: list[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                cmd = str(item.get("command") or "").strip()
                if cmd:
                    out.append(cmd)
        return out
    return []


def _hook_timeout_s(cfg: dict[str, Any]) -> int:
    raw = cfg.get("timeout_s") or os.getenv("AGENT_LAB_HOOK_TIMEOUT_S", "")
    try:
        return max(1, min(300, int(str(raw or DEFAULT_HOOK_TIMEOUT_S))))
    except (TypeError, ValueError):
        return DEFAULT_HOOK_TIMEOUT_S


def run_hook(event: str, context: dict[str, Any]) -> HookResult:
    """Run configured shell commands; exit 2 blocks with stderr/stdout as feedback."""
    cfg = load_hooks_config()
    commands = _commands_for_event(cfg, event)
    if not commands:
        return HookResult(blocked=False, feedback="", exit_code=0, event=event)

    payload = json.dumps(context, ensure_ascii=False)
    timeout = _hook_timeout_s(cfg)
    cwd = context.get("workspace")
    cwd_path = Path(str(cwd)).expanduser() if cwd else None

    for cmd in commands:
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                input=payload,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(cwd_path) if cwd_path and cwd_path.is_dir() else None,
            )
        except subprocess.TimeoutExpired:
            return HookResult(
                blocked=True,
                feedback=f"hook timeout ({timeout}s): {cmd[:80]}",
                exit_code=-1,
                event=event,
                command=cmd,
            )
        except OSError as e:
            return HookResult(
                blocked=True,
                feedback=f"hook failed to run: {e}",
                exit_code=-1,
                event=event,
                command=cmd,
            )

        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        feedback = err or out
        if proc.returncode == HOOK_EXIT_BLOCK:
            return HookResult(
                blocked=True,
                feedback=feedback or "hook blocked (exit 2)",
                exit_code=HOOK_EXIT_BLOCK,
                event=event,
                command=cmd,
            )
        if proc.returncode != 0 and proc.returncode is not None:
            return HookResult(
                blocked=True,
                feedback=feedback or f"hook exit {proc.returncode}",
                exit_code=int(proc.returncode),
                event=event,
                command=cmd,
            )
    return HookResult(blocked=False, feedback="", exit_code=0, event=event)


def _workspace_for_hooks(run_meta: dict[str, Any] | None, session_folder: Path | None) -> str:
    if session_folder and session_folder.is_dir():
        return str(session_folder.resolve())
    if run_meta:
        binding = run_meta.get("workspace_binding")
        if isinstance(binding, dict) and binding.get("path"):
            return str(binding["path"])
    from agent_lab.workspace_roots import primary_workspace

    perms = run_meta.get("permissions") if run_meta else None
    if not isinstance(perms, dict):
        perms = None
    return str(primary_workspace(perms))


class PreExecuteBlocked(Exception):
    """pre_execute hook blocked dry-run."""

    def __init__(self, message: str, *, pre_verify: dict[str, Any] | None = None):
        super().__init__(message)
        self.pre_verify = pre_verify or {}


def run_pre_execute_hooks(
    run_meta: dict[str, Any],
    action: dict[str, Any],
    *,
    session_folder: Path | None = None,
    session_id: str = "",
) -> dict[str, Any]:
    """Run pre_execute hooks before Cursor dry-run. exit 2 blocks."""
    ctx = {
        "event": "pre_execute",
        "session_id": session_id,
        "workspace": _workspace_for_hooks(run_meta, session_folder),
        "action": action,
        "team_lead": run_meta.get("team_lead"),
    }
    result = run_hook("pre_execute", ctx)
    return {
        "event": "pre_execute",
        "blocked": result.blocked,
        "feedback": result.feedback,
        "exit_code": result.exit_code,
        "command": result.command,
    }


def run_task_completed_hooks(
    run_meta: dict[str, Any],
    task: dict[str, Any],
    *,
    session_folder: Path | None = None,
    session_id: str = "",
) -> str | None:
    """Return block message for complete_task, or None if allowed."""
    ctx = {
        "event": "task_completed",
        "session_id": session_id,
        "workspace": _workspace_for_hooks(run_meta, session_folder),
        "task": task,
        "team_lead": run_meta.get("team_lead"),
    }
    result = run_hook("task_completed", ctx)
    if result.blocked:
        return result.feedback or "task_completed hook blocked"
    return None


def run_teammate_idle_hooks(
    run_meta: dict[str, Any],
    agent: str,
    *,
    session_folder: Path | None = None,
    session_id: str = "",
    in_progress_tasks: list[dict[str, Any]] | None = None,
) -> str | None:
    """Return peer-channel nudge text, or None."""
    agent_l = str(agent or "").strip().lower()
    tasks = in_progress_tasks or []
    from agent_lab.room_mailbox import unread_for_agent

    ctx = {
        "event": "teammate_idle",
        "session_id": session_id,
        "workspace": _workspace_for_hooks(run_meta, session_folder),
        "agent": agent_l,
        "in_progress_tasks": tasks,
        "mailbox_unread": len(unread_for_agent(run_meta, agent_l)),
    }
    result = run_hook("teammate_idle", ctx)
    if result.blocked and result.feedback.strip():
        return result.feedback.strip()
    if result.feedback.strip():
        return result.feedback.strip()
    if tasks:
        titles = ", ".join(
            str(t.get("title") or t.get("id") or "?")[:40] for t in tasks[:3]
        )
        return (
            f"담당 작업이 아직 in_progress입니다 ({titles}). "
            "완료·claim·MESSAGE로 handoff 하거나 [PROPOSED:]로 분해하세요."
        )
    return None
