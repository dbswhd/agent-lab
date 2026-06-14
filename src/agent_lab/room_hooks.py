"""Server-side room hooks (TaskCompleted, TeammateIdle) — not per-process .claude hooks."""

from __future__ import annotations

import json
import os
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

HOOK_EXIT_BLOCK = 2
DEFAULT_HOOK_TIMEOUT_S = 30

SubReason = Literal[
    "",
    "exit_2",
    "timeout",
    "os_error",
    "nonzero",
    "envelope_invalid",
]


# Shipped events — normative policy (see docs/HOOK-COMMUNICATE-REFORM.md §5).
@dataclass(frozen=True)
class HookEventPolicy:
    """How run_hook() treats exit codes and subprocess failures."""

    block_on_exit_2: bool
    block_on_nonzero: bool
    block_on_timeout: bool
    block_on_os_error: bool
    stop_on_block: bool  # multi-command: False = run-all then aggregate


_SHIPPED_EVENT_POLICIES: dict[str, HookEventPolicy] = {
    # Dry-run / task completion — fail closed.
    "pre_execute": HookEventPolicy(True, True, True, True, stop_on_block=True),
    "task_completed": HookEventPolicy(True, True, True, True, stop_on_block=True),
    # Peer nudge — never abort the room turn; exit 2 still surfaces feedback.
    "teammate_idle": HookEventPolicy(
        block_on_exit_2=False,
        block_on_nonzero=False,
        block_on_timeout=False,
        block_on_os_error=False,
        stop_on_block=False,
    ),
}

_TARGET_EVENT_POLICIES: dict[str, HookEventPolicy] = {
    "pre_agent_reply": HookEventPolicy(
        block_on_exit_2=False,
        block_on_nonzero=False,
        block_on_timeout=False,
        block_on_os_error=False,
        stop_on_block=False,
    ),
    "post_agent_reply": HookEventPolicy(
        block_on_exit_2=True,
        block_on_nonzero=False,
        block_on_timeout=False,
        block_on_os_error=False,
        stop_on_block=True,
    ),
    "post_harvest": HookEventPolicy(
        block_on_exit_2=False,
        block_on_nonzero=False,
        block_on_timeout=False,
        block_on_os_error=False,
        stop_on_block=False,
    ),
    "pre_scribe": HookEventPolicy(
        block_on_exit_2=True,
        block_on_nonzero=False,
        block_on_timeout=True,
        block_on_os_error=True,
        stop_on_block=True,
    ),
    "pre_dispatch": HookEventPolicy(True, True, True, True, stop_on_block=True),
    "post_dispatch": HookEventPolicy(
        block_on_exit_2=False,
        block_on_nonzero=False,
        block_on_timeout=False,
        block_on_os_error=False,
        stop_on_block=False,
    ),
}

_DEFAULT_POLICY = HookEventPolicy(True, True, True, True, stop_on_block=True)


@dataclass
class HookResult:
    blocked: bool
    feedback: str
    exit_code: int
    event: str
    command: str = ""
    sub_reason: SubReason = ""
    retryable: bool = False
    structured: dict[str, Any] | None = None


_CONFIG_CACHE: dict[str, Any] | None = None
_CONFIG_CACHE_KEY: tuple[str, ...] = ()


def clear_hooks_config_cache() -> None:
    """Test helper — invalidate cached hooks.toml."""
    global _CONFIG_CACHE, _CONFIG_CACHE_KEY
    _CONFIG_CACHE = None
    _CONFIG_CACHE_KEY = ()


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


def _config_cache_key() -> tuple[str, ...]:
    key: list[str] = []
    for path in hooks_config_paths():
        if path.is_file():
            try:
                stat = path.stat()
                key.append(f"{path}:{stat.st_mtime_ns}:{stat.st_size}")
            except OSError:
                key.append(f"{path}:missing")
        else:
            key.append(f"{path}:absent")
    return tuple(key)


def load_hooks_config(*, force_reload: bool = False) -> dict[str, Any]:
    """Load first existing hooks.toml. Cached by path + mtime until force_reload."""
    global _CONFIG_CACHE, _CONFIG_CACHE_KEY
    cache_key = _config_cache_key()
    if not force_reload and _CONFIG_CACHE is not None and _CONFIG_CACHE_KEY == cache_key:
        return dict(_CONFIG_CACHE)
    for path in hooks_config_paths():
        if path.is_file():
            try:
                data = tomllib.loads(path.read_text(encoding="utf-8"))
                parsed = data if isinstance(data, dict) else {}
                _CONFIG_CACHE = parsed
                _CONFIG_CACHE_KEY = cache_key
                return dict(parsed)
            except (OSError, ValueError):
                continue
    _CONFIG_CACHE = {}
    _CONFIG_CACHE_KEY = cache_key
    return {}


def _event_policy(event: str, cfg: dict[str, Any] | None = None) -> HookEventPolicy:
    base = _SHIPPED_EVENT_POLICIES.get(event) or _TARGET_EVENT_POLICIES.get(event) or _DEFAULT_POLICY
    if not cfg:
        return base
    policy_root = cfg.get("policy")
    if not isinstance(policy_root, dict):
        return base
    override = policy_root.get(event)
    if not isinstance(override, dict):
        return base
    fail_on = override.get("fail_on")
    if isinstance(fail_on, list):
        fail_set = {str(x).strip() for x in fail_on}
        return HookEventPolicy(
            block_on_exit_2=(
                "exit_2" in fail_set if fail_set else bool(override.get("block_on_exit_2", base.block_on_exit_2))
            ),
            block_on_nonzero=(
                "nonzero" in fail_set or "exit_nonzero" in fail_set
                if fail_set
                else bool(override.get("block_on_nonzero", base.block_on_nonzero))
            ),
            block_on_timeout=(
                "timeout" in fail_set if fail_set else bool(override.get("block_on_timeout", base.block_on_timeout))
            ),
            block_on_os_error=(
                "os_error" in fail_set if fail_set else bool(override.get("block_on_os_error", base.block_on_os_error))
            ),
            stop_on_block=bool(override.get("stop_on_block", base.stop_on_block)),
        )
    return HookEventPolicy(
        block_on_exit_2=bool(override.get("block_on_exit_2", base.block_on_exit_2)),
        block_on_nonzero=bool(override.get("block_on_nonzero", base.block_on_nonzero)),
        block_on_timeout=bool(override.get("block_on_timeout", base.block_on_timeout)),
        block_on_os_error=bool(override.get("block_on_os_error", base.block_on_os_error)),
        stop_on_block=bool(override.get("stop_on_block", base.stop_on_block)),
    )


def _commands_from_raw(raw: Any) -> list[str]:
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


def _commands_for_event(cfg: dict[str, Any], event: str) -> list[str]:
    hooks = cfg.get("hooks")
    if not isinstance(hooks, dict):
        return []
    return _commands_from_raw(hooks.get(event))


def _commands_for_agent_event(cfg: dict[str, Any], agent: str, event: str) -> list[str]:
    """Resolve hooks.<agent>.<event> → hooks.global.<event> → legacy hooks.<event>."""
    hooks = cfg.get("hooks")
    if not isinstance(hooks, dict):
        return []
    agent_l = str(agent or "").strip().lower()
    agent_section = hooks.get(agent_l)
    if isinstance(agent_section, dict):
        cmds = _commands_from_raw(agent_section.get(event))
        if cmds:
            return cmds
    global_section = hooks.get("global")
    if isinstance(global_section, dict):
        cmds = _commands_from_raw(global_section.get(event))
        if cmds:
            return cmds
    return _commands_for_event(cfg, event)


def _hook_timeout_s(cfg: dict[str, Any]) -> int:
    raw = cfg.get("timeout_s") or os.getenv("AGENT_LAB_HOOK_TIMEOUT_S", "")
    try:
        return max(1, min(300, int(str(raw or DEFAULT_HOOK_TIMEOUT_S))))
    except (TypeError, ValueError):
        return DEFAULT_HOOK_TIMEOUT_S


def _merge_feedback(existing: str, new: str) -> str:
    new = (new or "").strip()
    if not new:
        return existing
    if not existing:
        return new
    return f"{existing}\n{new}"


def run_hook(
    event: str,
    context: dict[str, Any],
    *,
    agent: str | None = None,
) -> HookResult:
    """Run configured shell commands; exit 2 blocks with stderr/stdout as feedback.

    Event-specific policy: see ``HookEventPolicy`` / docs/HOOK-COMMUNICATE-REFORM.md §5.
    When ``agent`` is set, resolves per-agent hook sections first.
    """
    cfg = load_hooks_config()
    if agent:
        commands = _commands_for_agent_event(cfg, agent, event)
    else:
        commands = _commands_for_event(cfg, event)
    if not commands:
        return HookResult(blocked=False, feedback="", exit_code=0, event=event)

    policy = _event_policy(event, cfg)
    payload = json.dumps(context, ensure_ascii=False)
    timeout = _hook_timeout_s(cfg)
    cwd = context.get("workspace")
    cwd_path = Path(str(cwd)).expanduser() if cwd else None

    blocked = False
    feedback = ""
    last_exit = 0
    last_command = ""
    last_sub_reason: SubReason = ""

    for cmd in commands:
        last_command = cmd
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
            last_exit = -1
            last_sub_reason = "timeout"
            msg = f"hook timeout ({timeout}s): {cmd[:80]}"
            feedback = _merge_feedback(feedback, msg)
            if policy.block_on_timeout:
                blocked = True
                if policy.stop_on_block:
                    break
            continue
        except OSError as e:
            last_exit = -1
            last_sub_reason = "os_error"
            msg = f"hook failed to run: {e}"
            feedback = _merge_feedback(feedback, msg)
            if policy.block_on_os_error:
                blocked = True
                if policy.stop_on_block:
                    break
            continue

        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        cmd_feedback = err or out
        last_exit = int(proc.returncode or 0)

        if proc.returncode == HOOK_EXIT_BLOCK:
            last_sub_reason = "exit_2"
            if cmd_feedback:
                feedback = _merge_feedback(feedback, cmd_feedback)
            if policy.block_on_exit_2:
                blocked = True
                if not feedback:
                    feedback = "hook blocked (exit 2)"
                if policy.stop_on_block:
                    break
            continue

        if proc.returncode not in (0, None):
            last_sub_reason = "nonzero"
            if cmd_feedback:
                feedback = _merge_feedback(feedback, cmd_feedback)
            elif not feedback:
                feedback = f"hook exit {proc.returncode}"
            if policy.block_on_nonzero:
                blocked = True
                if policy.stop_on_block:
                    break
            continue

        if cmd_feedback:
            feedback = _merge_feedback(feedback, cmd_feedback)

    return HookResult(
        blocked=blocked,
        feedback=feedback.strip(),
        exit_code=last_exit,
        event=event,
        command=last_command,
        sub_reason=last_sub_reason,
        retryable=blocked and event == "post_agent_reply",
    )


def run_hook_for_agent(
    event: str,
    agent: str,
    context: dict[str, Any],
) -> HookResult:
    """Run hooks for a specific agent id (Room Hook Router)."""
    ctx = dict(context)
    ctx.setdefault("agent", str(agent).strip().lower())
    ctx.setdefault("event", event)
    return run_hook(event, ctx, agent=agent)


def _hook_run_record(
    result: HookResult,
    *,
    agent: str = "",
    session_id: str = "",
    human_turn: int | None = None,
    parallel_round: int | None = None,
    dispatch_id: str | None = None,
) -> dict[str, Any]:
    from datetime import datetime, timezone

    rec: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": result.event,
        "agent": agent or None,
        "command": result.command,
        "exit_code": result.exit_code,
        "sub_reason": result.sub_reason,
        "blocked": result.blocked,
        "feedback": result.feedback[:500] if result.feedback else "",
        "session_id": session_id or None,
    }
    if human_turn is not None:
        rec["human_turn"] = human_turn
    if parallel_round is not None:
        rec["parallel_round"] = parallel_round
    if dispatch_id:
        rec["dispatch_id"] = dispatch_id
    if result.structured:
        rec["structured"] = result.structured
    return rec


def run_pre_agent_reply_hooks(
    run_meta: dict[str, Any],
    agent: str,
    *,
    session_folder: Path | None = None,
    session_id: str = "",
    parallel_round: int = 1,
    consensus_mode: bool = False,
    review_mode: bool = False,
    turn_profile: str = "",
    gate_snapshot: dict[str, Any] | None = None,
    human_turn: int | None = None,
) -> HookResult:
    from agent_lab.runtime.policy import PolicyEngine

    snap = gate_snapshot if gate_snapshot is not None else PolicyEngine.gate_snapshot(run_meta)
    ctx = {
        "event": "pre_agent_reply",
        "session_id": session_id,
        "workspace": _workspace_for_hooks(run_meta, session_folder),
        "agent": str(agent).strip().lower(),
        "parallel_round": parallel_round,
        "consensus_mode": consensus_mode,
        "review_mode": review_mode,
        "turn_profile": turn_profile,
        "gate_snapshot": snap,
        "team_lead": run_meta.get("team_lead"),
    }
    return run_hook_for_agent("pre_agent_reply", agent, ctx)


def _builtin_post_agent_reply_envelope_check(
    *,
    parallel_round: int,
    consensus_mode: bool,
    review_mode: bool,
    turn_profile: str,
    envelope: dict[str, Any] | None,
    envelope_parse_error: bool,
) -> HookResult | None:
    from agent_lab.reply_policy import resolve_reply_policy

    policy = resolve_reply_policy(
        parallel_round=parallel_round,
        review_mode=review_mode,
        consensus_mode=consensus_mode,
        turn_profile=turn_profile,
    )
    if not policy.envelope_strict or policy.parallel_round < 2:
        return None
    act = envelope.get("act") if isinstance(envelope, dict) else None
    if envelope_parse_error or not act:
        detail = (
            "Envelope parse failed — use JSON line 1 or ```agent-envelope fenced JSON."
            if envelope_parse_error
            else "Consensus/review R2+ requires envelope act (e.g. ENDORSE, PASS)."
        )
        return HookResult(
            blocked=True,
            feedback=detail,
            exit_code=0,
            event="post_agent_reply",
            sub_reason="envelope_invalid",
            retryable=consensus_mode,
        )
    return None


def run_post_agent_reply_hooks(
    run_meta: dict[str, Any],
    agent: str,
    *,
    content: str,
    envelope: dict[str, Any] | None,
    envelope_parse_error: bool,
    session_folder: Path | None = None,
    session_id: str = "",
    parallel_round: int = 1,
    consensus_mode: bool = False,
    review_mode: bool = False,
    turn_profile: str = "",
    gate_snapshot: dict[str, Any] | None = None,
    human_turn: int | None = None,
) -> HookResult:
    from agent_lab.runtime.policy import PolicyEngine

    snap = gate_snapshot if gate_snapshot is not None else PolicyEngine.gate_snapshot(run_meta)
    ctx = {
        "event": "post_agent_reply",
        "session_id": session_id,
        "workspace": _workspace_for_hooks(run_meta, session_folder),
        "agent": str(agent).strip().lower(),
        "content": content,
        "envelope": envelope,
        "envelope_parse_error": envelope_parse_error,
        "parallel_round": parallel_round,
        "consensus_mode": consensus_mode,
        "review_mode": review_mode,
        "turn_profile": turn_profile,
        "gate_snapshot": snap,
        "team_lead": run_meta.get("team_lead"),
    }
    builtin = _builtin_post_agent_reply_envelope_check(
        parallel_round=parallel_round,
        consensus_mode=consensus_mode,
        review_mode=review_mode,
        turn_profile=turn_profile,
        envelope=envelope,
        envelope_parse_error=envelope_parse_error,
    )
    result = run_hook_for_agent("post_agent_reply", agent, ctx)
    if builtin and builtin.blocked:
        if result.feedback.strip():
            builtin = HookResult(
                blocked=True,
                feedback=_merge_feedback(builtin.feedback, result.feedback),
                exit_code=result.exit_code,
                event=builtin.event,
                command=result.command,
                sub_reason=builtin.sub_reason,
                retryable=builtin.retryable,
                structured=result.structured,
            )
        if result.blocked and not consensus_mode:
            return HookResult(
                blocked=False,
                feedback=result.feedback,
                exit_code=result.exit_code,
                event=result.event,
                command=result.command,
                sub_reason=result.sub_reason,
                retryable=False,
            )
        return builtin
    if result.blocked and not consensus_mode:
        return HookResult(
            blocked=False,
            feedback=result.feedback,
            exit_code=result.exit_code,
            event=result.event,
            command=result.command,
            sub_reason=result.sub_reason,
            retryable=False,
        )
    return result


def run_pre_dispatch_hooks(
    run_meta: dict[str, Any],
    *,
    session_folder: Path | None = None,
    session_id: str = "",
    human_turn: int | None = None,
    dispatch_id: str = "",
    dispatch_op: str = "",
    dispatch_agents: list[str] | None = None,
    prompt: str = "",
    topic_route: dict[str, Any] | None = None,
) -> HookResult:
    from agent_lab.runtime.policy import PolicyEngine

    ctx = {
        "event": "pre_dispatch",
        "session_id": session_id,
        "workspace": _workspace_for_hooks(run_meta, session_folder),
        "human_turn": human_turn,
        "dispatch_id": dispatch_id,
        "dispatch_op": dispatch_op,
        "dispatch_agents": list(dispatch_agents or []),
        "prompt": prompt[:500],
        "topic_route": topic_route,
        "gate_snapshot": PolicyEngine.gate_snapshot(run_meta),
        "team_lead": run_meta.get("team_lead"),
    }
    return run_hook("pre_dispatch", ctx)


def run_post_dispatch_hooks(
    run_meta: dict[str, Any],
    *,
    session_folder: Path | None = None,
    session_id: str = "",
    human_turn: int | None = None,
    dispatch_id: str = "",
    dispatch_op: str = "",
    dispatch_agents: list[str] | None = None,
    topic_route: dict[str, Any] | None = None,
) -> HookResult:
    from agent_lab.runtime.policy import PolicyEngine

    ctx = {
        "event": "post_dispatch",
        "session_id": session_id,
        "workspace": _workspace_for_hooks(run_meta, session_folder),
        "human_turn": human_turn,
        "dispatch_id": dispatch_id,
        "dispatch_op": dispatch_op,
        "dispatch_agents": list(dispatch_agents or []),
        "topic_route": topic_route,
        "gate_snapshot": PolicyEngine.gate_snapshot(run_meta),
        "team_lead": run_meta.get("team_lead"),
    }
    return run_hook("post_dispatch", ctx)


def run_post_harvest_hooks(
    run_meta: dict[str, Any],
    *,
    session_folder: Path | None = None,
    session_id: str = "",
    human_turn: int | None = None,
    mode: str = "discuss",
) -> HookResult:
    from agent_lab.runtime.policy import PolicyEngine

    ctx = {
        "event": "post_harvest",
        "session_id": session_id,
        "workspace": _workspace_for_hooks(run_meta, session_folder),
        "human_turn": human_turn,
        "mode": mode,
        "gate_snapshot": PolicyEngine.gate_snapshot(run_meta),
        "team_lead": run_meta.get("team_lead"),
    }
    return run_hook("post_harvest", ctx)


def run_pre_scribe_hooks(
    run_meta: dict[str, Any],
    *,
    session_folder: Path | None = None,
    session_id: str = "",
    trigger: str = "auto_turn",
    message_count: int = 0,
) -> HookResult:
    from agent_lab.runtime.policy import PolicyEngine

    ctx = {
        "event": "pre_scribe",
        "session_id": session_id,
        "workspace": _workspace_for_hooks(run_meta, session_folder),
        "trigger": trigger,
        "message_count": message_count,
        "gate_snapshot": PolicyEngine.gate_snapshot(run_meta),
        "team_lead": run_meta.get("team_lead"),
    }
    return run_hook("pre_scribe", ctx)


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
        "sub_reason": result.sub_reason,
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
    if result.feedback.strip():
        return result.feedback.strip()
    if tasks:
        titles = ", ".join(str(t.get("title") or t.get("id") or "?")[:40] for t in tasks[:3])
        return (
            f"담당 작업이 아직 in_progress입니다 ({titles}). "
            "완료·claim·MESSAGE로 handoff 하거나 [PROPOSED:]로 분해하세요."
        )
    return None
