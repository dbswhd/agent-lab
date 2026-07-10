"""ABSORB P1-fork — clone session context into a new folder (no gate bypass)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.run.meta import read_run_meta, write_run_meta
from agent_lab.session import session_dir
from agent_lab.session.paths import active_sessions_dir
from agent_lab.session.setup import seed_session_setup

_COPY_RUN_KEYS = (
    "workspace_preset",
    "session_template",
    "workspace_binding",
    "session_phase",
    "layout_frozen",
    "agent_thread_bindings",
    "room_models",
    "autonomy_level",
    "autonomy_ceiling",
    "response_contract",
)

_DEFAULT_CHAT_TAIL = 80


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_topic(folder: Path) -> str:
    path = folder / "topic.txt"
    if not path.is_file():
        return folder.name
    return path.read_text(encoding="utf-8").strip() or folder.name


def _copy_chat_tail(src: Path, dest: Path, *, limit: int) -> int:
    chat = src / "chat.jsonl"
    if not chat.is_file() or limit <= 0:
        return 0
    try:
        lines = [ln for ln in chat.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except OSError:
        return 0
    tail = lines[-limit:]
    if not tail:
        return 0
    (dest / "chat.jsonl").write_text("\n".join(tail) + "\n", encoding="utf-8")
    return len(tail)


def fork_session(
    source: Path,
    *,
    copy_plan: bool = True,
    chat_tail: int = _DEFAULT_CHAT_TAIL,
    topic_suffix: str = " (fork)",
) -> dict[str, Any]:
    """Create a new session from ``source``.

    Copies topic/plan/setup + trimmed chat. Does **not** copy pending inbox,
    executions, merge state, or steer queue — Human must re-approve gates.
    """
    if not source.is_dir():
        raise FileNotFoundError(f"session not found: {source}")

    src_run = read_run_meta(source)
    topic = _read_topic(source)
    fork_topic = f"{topic}{topic_suffix}" if topic_suffix else topic

    dest = session_dir(fork_topic, base=active_sessions_dir())
    (dest / "topic.txt").write_text(fork_topic + "\n", encoding="utf-8")

    workspace_id = None
    workspace_path = None
    binding = src_run.get("workspace_binding")
    if isinstance(binding, dict):
        workspace_id = binding.get("id") or src_run.get("workspace_preset")
        workspace_path = binding.get("path")
    else:
        workspace_id = src_run.get("workspace_preset")

    template = src_run.get("session_template")
    bindings = src_run.get("agent_thread_bindings")
    thread_bindings = bindings if isinstance(bindings, dict) else None

    seed_session_setup(
        dest,
        workspace_id=str(workspace_id) if workspace_id else None,
        session_template=str(template) if template else None,
        workspace_path=str(workspace_path) if workspace_path else None,
        topic=fork_topic,
        agent_thread_bindings=thread_bindings,
    )

    new_run = read_run_meta(dest)
    for key in _COPY_RUN_KEYS:
        if key in src_run and src_run[key] is not None:
            new_run[key] = src_run[key]
    new_run["forked_from"] = {
        "session_id": source.name,
        "at": _now_iso(),
        "copy_plan": bool(copy_plan),
        "chat_tail": int(chat_tail),
    }
    # Explicitly clear gate-bearing surfaces if seed somehow carried them.
    for drop in (
        "executions",
        "human_inbox",
        "steer_queue",
        "pending_plans",
        "consensus_agreements",
        "schedule_sandbox",
        "monitor_merge_checks_fp",
    ):
        new_run.pop(drop, None)
    write_run_meta(dest, new_run)

    plan_copied = False
    if copy_plan:
        src_plan = source / "plan.md"
        if src_plan.is_file() and src_plan.stat().st_size > 0:
            shutil.copy2(src_plan, dest / "plan.md")
            plan_copied = True

    chat_lines = _copy_chat_tail(source, dest, limit=max(0, int(chat_tail)))

    meta_path = dest / "meta.json"
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}
    meta["topic"] = fork_topic
    meta["forked_from"] = new_run["forked_from"]
    meta_path.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return {
        "ok": True,
        "session_id": dest.name,
        "folder": str(dest),
        "forked_from": source.name,
        "topic": fork_topic,
        "plan_copied": plan_copied,
        "chat_lines": chat_lines,
    }
