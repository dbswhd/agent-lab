"""Room Dispatch Protocol (RDP) — scoped worker fan-out within discuss lane (CMD-RDP)."""

from __future__ import annotations

import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from agent_lab.agents.registry import AGENT_IDS
from agent_lab.room.agent_invoke import _call_one_agent
from agent_lab.room.messages import ChatMessage
from agent_lab.room.session_persist import _session_context

DispatchOp = Literal["single_delegate", "parallel_delegate", "synthesize"]

_DELEGATE_RE = re.compile(
    r"(?:^|\n)\s*DELEGATE\s+(cursor|codex|claude)\s*:\s*"
    r'(?:"([^"]{4,2000})"|([^\n]{4,2000}))',
    re.I | re.M,
)

_PARALLEL_DISPATCH_RE = re.compile(
    r"(?:^|\n)\s*DISPATCH\s+parallel\s*:\s*"
    r"((?:cursor|codex|claude)(?:\s*,\s*(?:cursor|codex|claude))*)\s*:\s*"
    r'(?:"([^"]{4,2000})"|([^\n]{4,2000}))',
    re.I | re.M,
)


@dataclass(frozen=True)
class DispatchRequest:
    op: DispatchOp
    agents: tuple[str, ...]
    prompt: str
    issuer: str = "human"
    trimmed_agents: tuple[str, ...] = ()


def dispatch_max_fanout() -> int:
    raw = (os.getenv("AGENT_LAB_DISPATCH_MAX_FANOUT") or "3").strip()
    try:
        return max(1, min(3, int(raw)))
    except ValueError:
        return 3


def parse_delegate_from_message(text: str) -> dict[str, str] | None:
    m = _DELEGATE_RE.search(text or "")
    if not m:
        return None
    agent = m.group(1).strip().lower()
    prompt = (m.group(2) or m.group(3) or "").strip()
    if agent not in AGENT_IDS or len(prompt) < 4:
        return None
    return {"agent": agent, "prompt": prompt}


def _parse_agent_list(raw: str) -> list[str]:
    seen: list[str] = []
    for part in re.split(r"\s*,\s*", raw or ""):
        aid = part.strip().lower()
        if aid in AGENT_IDS and aid not in seen:
            seen.append(aid)
    return seen


def parse_dispatch_from_message(text: str) -> DispatchRequest | None:
    """Precedence: DELEGATE (single) then DISPATCH parallel."""
    single = parse_delegate_from_message(text)
    if single:
        return DispatchRequest(
            op="single_delegate",
            agents=(single["agent"],),
            prompt=single["prompt"],
        )
    m = _PARALLEL_DISPATCH_RE.search(text or "")
    if not m:
        return None
    agents = _parse_agent_list(m.group(1))
    prompt = (m.group(2) or m.group(3) or "").strip()
    if len(agents) < 2 or len(prompt) < 4:
        return None
    cap = dispatch_max_fanout()
    trimmed: tuple[str, ...] = ()
    if len(agents) > cap:
        trimmed = tuple(agents[cap:])
        agents = agents[:cap]
    return DispatchRequest(
        op="parallel_delegate",
        agents=tuple(agents),
        prompt=prompt,
        trimmed_agents=trimmed,
    )


def next_dispatch_id(run_meta: dict[str, Any]) -> str:
    ledger = run_meta.get("dispatch_ledger") or []
    n = len(ledger) if isinstance(ledger, list) else 0
    return f"disp-{n + 1:03d}"


def append_dispatch_ledger(run_meta: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    rows = list(run_meta.get("dispatch_ledger") or [])
    rows.append(entry)
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(run_meta, dispatch_ledger=rows[-100:])
    return entry


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _topic_category_meta(run_meta: dict[str, Any]) -> str | None:
    cat = run_meta.get("_turn_category")
    if isinstance(cat, dict):
        return str(cat.get("value") or "") or None
    if isinstance(cat, str) and cat.strip():
        return cat.strip()
    return None


def _emit_dispatch_events(
    on_event: Callable[[str, dict[str, Any]], None] | None,
    typ: str,
    payload: dict[str, Any],
) -> None:
    if not on_event:
        return
    on_event(typ, payload)
    if typ == "dispatch_start":
        on_event("delegate_start", payload)
    elif typ == "dispatch_done":
        on_event("delegate_done", payload)


def _run_pre_post_dispatch_hooks(
    *,
    event: str,
    run_meta: dict[str, Any],
    folder: Path,
    dispatch_id: str,
    dispatch_op: str,
    dispatch_agents: list[str],
    prompt: str,
    human_turn: int,
    on_event: Callable[[str, dict[str, Any]], None] | None,
) -> tuple[bool, str]:
    from agent_lab.room.hooks import (
        _hook_run_record,
        run_post_dispatch_hooks,
        run_pre_dispatch_hooks,
    )
    from agent_lab.run.meta import append_hook_run

    topic_route = run_meta.get("_turn_category")
    if event == "pre_dispatch":
        hook = run_pre_dispatch_hooks(
            run_meta,
            session_folder=folder,
            session_id=folder.name,
            human_turn=human_turn,
            dispatch_id=dispatch_id,
            dispatch_op=dispatch_op,
            dispatch_agents=dispatch_agents,
            prompt=prompt[:500],
            topic_route=topic_route if isinstance(topic_route, dict) else None,
        )
    else:
        hook = run_post_dispatch_hooks(
            run_meta,
            session_folder=folder,
            session_id=folder.name,
            human_turn=human_turn,
            dispatch_id=dispatch_id,
            dispatch_op=dispatch_op,
            dispatch_agents=dispatch_agents,
            topic_route=topic_route if isinstance(topic_route, dict) else None,
        )
    rec = _hook_run_record(
        hook,
        session_id=folder.name,
        human_turn=human_turn,
        dispatch_id=dispatch_id,
    )
    append_hook_run(folder, rec, run_meta=run_meta)
    if on_event:
        on_event(
            "hook_event",
            {
                "event": hook.event,
                "blocked": hook.blocked,
                "feedback": hook.feedback,
                "sub_reason": hook.sub_reason,
                "dispatch_id": dispatch_id,
            },
        )
    return hook.blocked, hook.feedback


def _call_one_delegate_worker(
    *,
    agent_id: str,
    topic: str,
    messages: list[Any],
    run_meta: dict[str, Any],
    folder: Path,
    prompt: str,
    permissions: dict | None,
    on_event: Callable[[str, dict[str, Any]], None] | None,
    human_turn: int,
    dispatch_label: str,
) -> tuple[Any, dict[str, Any]]:
    plan_md, _ = _session_context(folder)
    msg = _call_one_agent(
        agent_id,  # type: ignore[arg-type]
        topic=topic,
        thread=messages,
        parallel_round=1,
        permissions=permissions,
        review_mode=False,
        review_advocate=None,
        plan_md=plan_md,
        run_meta=run_meta,
        on_event=on_event,
        extra_follow_up=(
            f"[{dispatch_label} · scoped task]\n{prompt.strip()}\n\n"
            "이번 호출만 수행하고 결과를 ```artifact 블록 또는 요약으로 반환하세요."
        ),
    )
    from agent_lab.room.artifacts import append_artifact

    body = msg.content or ""
    art = append_artifact(
        run_meta,
        producer=agent_id,
        kind="delegate",
        summary=f"{dispatch_label}: {prompt[:120]}",
        body=body,
        session_folder=folder,
        human_turn=human_turn,
        parallel_round=1,
        refs=["delegate", "dispatch"],
    )
    peer = ChatMessage(
        role="system",
        agent=None,
        content=(
            f"[dispatch · {agent_id}]\n"
            f"task: {prompt[:300]}\n"
            f"artifact: {art.get('id')} — {(art.get('summary') or '')[:200]}"
        ),
        visibility="peer",
        parallel_round=1,
    )
    worker_meta = {
        "agent": agent_id,
        "prompt": prompt,
        "artifact_id": art.get("id"),
    }
    return (msg, peer), worker_meta


def run_single_delegate(
    *,
    topic: str,
    messages: list[Any],
    run_meta: dict[str, Any],
    folder: Path,
    agent: str,
    prompt: str,
    permissions: dict | None,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
    human_turn: int = 1,
    issuer: str = "human",
) -> tuple[list[Any], dict[str, Any]]:
    dispatch_id = next_dispatch_id(run_meta)
    agents = [agent.strip().lower()]
    _emit_dispatch_events(
        on_event,
        "dispatch_start",
        {
            "dispatch_id": dispatch_id,
            "op": "single_delegate",
            "agents": agents,
            "prompt": prompt[:200],
        },
    )
    blocked, feedback = _run_pre_post_dispatch_hooks(
        event="pre_dispatch",
        run_meta=run_meta,
        folder=folder,
        dispatch_id=dispatch_id,
        dispatch_op="single_delegate",
        dispatch_agents=agents,
        prompt=prompt,
        human_turn=human_turn,
        on_event=on_event,
    )
    if blocked:
        entry = append_dispatch_ledger(
            run_meta,
            {
                "id": dispatch_id,
                "op": "single_delegate",
                "issuer": issuer,
                "agents": agents,
                "prompt": prompt,
                "status": "blocked",
                "blocked_reason": feedback[:500],
                "started_at": _utc_now(),
                "ended_at": _utc_now(),
                "topic_category": _topic_category_meta(run_meta),
            },
        )
        _emit_dispatch_events(
            on_event,
            "dispatch_done",
            {"dispatch_id": dispatch_id, "status": "blocked", **entry},
        )
        return [], {"dispatch_id": dispatch_id, "blocked": True, "replaced_full_round": True}

    (msg, peer), worker_meta = _call_one_delegate_worker(
        agent_id=agents[0],
        topic=topic,
        messages=messages,
        run_meta=run_meta,
        folder=folder,
        prompt=prompt,
        permissions=permissions,
        on_event=on_event,
        human_turn=human_turn,
        dispatch_label="DELEGATE",
    )
    meta = {
        **worker_meta,
        "dispatch_id": dispatch_id,
        "op": "single_delegate",
        "replaced_full_round": True,
    }
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(run_meta, last_delegate=meta)
    entry = append_dispatch_ledger(
        run_meta,
        {
            "id": dispatch_id,
            "op": "single_delegate",
            "issuer": issuer,
            "agents": agents,
            "prompt": prompt,
            "status": "done",
            "artifact_ids": [worker_meta.get("artifact_id")],
            "started_at": _utc_now(),
            "ended_at": _utc_now(),
            "topic_category": _topic_category_meta(run_meta),
        },
    )
    _run_pre_post_dispatch_hooks(
        event="post_dispatch",
        run_meta=run_meta,
        folder=folder,
        dispatch_id=dispatch_id,
        dispatch_op="single_delegate",
        dispatch_agents=agents,
        prompt=prompt,
        human_turn=human_turn,
        on_event=on_event,
    )
    _emit_dispatch_events(
        on_event,
        "dispatch_done",
        {"dispatch_id": dispatch_id, "status": "done", **meta},
    )
    return [msg, peer], meta


def run_parallel_delegate(
    *,
    topic: str,
    messages: list[Any],
    run_meta: dict[str, Any],
    folder: Path,
    agents: list[str],
    prompt: str,
    permissions: dict | None,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
    human_turn: int = 1,
    issuer: str = "human",
    trimmed_agents: list[str] | None = None,
) -> tuple[list[Any], dict[str, Any]]:
    dispatch_id = next_dispatch_id(run_meta)
    agent_list = [a.strip().lower() for a in agents if a.strip()]
    trimmed = list(trimmed_agents or [])

    _emit_dispatch_events(
        on_event,
        "dispatch_start",
        {
            "dispatch_id": dispatch_id,
            "op": "parallel_delegate",
            "agents": agent_list,
            "trimmed_agents": trimmed,
            "prompt": prompt[:200],
        },
    )

    pre_blocked, feedback = _run_pre_post_dispatch_hooks(
        event="pre_dispatch",
        run_meta=run_meta,
        folder=folder,
        dispatch_id=dispatch_id,
        dispatch_op="parallel_delegate",
        dispatch_agents=agent_list,
        prompt=prompt,
        human_turn=human_turn,
        on_event=on_event,
    )
    if pre_blocked:
        append_dispatch_ledger(
            run_meta,
            {
                "id": dispatch_id,
                "op": "parallel_delegate",
                "issuer": issuer,
                "agents": agent_list,
                "prompt": prompt,
                "status": "blocked",
                "blocked_reason": feedback[:500],
                "started_at": _utc_now(),
                "ended_at": _utc_now(),
                "topic_category": _topic_category_meta(run_meta),
            },
        )
        _emit_dispatch_events(
            on_event,
            "dispatch_done",
            {"dispatch_id": dispatch_id, "status": "blocked"},
        )
        return [], {"dispatch_id": dispatch_id, "blocked": True, "replaced_full_round": True}

    replies: list[Any] = []
    artifact_ids: list[str] = []
    workers: list[dict[str, Any]] = []

    def _worker(aid: str) -> tuple[str, Any, Any, dict[str, Any]]:
        pair, wmeta = _call_one_delegate_worker(
            agent_id=aid,
            topic=topic,
            messages=messages,
            run_meta=run_meta,
            folder=folder,
            prompt=prompt,
            permissions=permissions,
            on_event=on_event,
            human_turn=human_turn,
            dispatch_label="DISPATCH",
        )
        return aid, pair[0], pair[1], wmeta

    meta_lock = threading.Lock()

    def _worker_locked(aid: str) -> tuple[str, Any, Any, dict[str, Any]]:
        with meta_lock:
            return _worker(aid)

    with ThreadPoolExecutor(max_workers=len(agent_list)) as pool:
        futures = {pool.submit(_worker_locked, aid): aid for aid in agent_list}
        for fut in as_completed(futures):
            _aid, msg, peer, wmeta = fut.result()
            replies.extend([msg, peer])
            artifact_ids.append(str(wmeta.get("artifact_id") or ""))
            workers.append(wmeta)

    meta = {
        "dispatch_id": dispatch_id,
        "op": "parallel_delegate",
        "agents": agent_list,
        "prompt": prompt,
        "artifact_ids": artifact_ids,
        "workers": workers,
        "replaced_full_round": True,
    }
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(
        run_meta,
        last_delegate={
            "agent": agent_list[0] if len(agent_list) == 1 else None,
            "agents": agent_list,
            "prompt": prompt,
            "artifact_ids": artifact_ids,
            "replaced_full_round": True,
            "dispatch_id": dispatch_id,
        },
    )
    ledger_entry: dict[str, Any] = {
        "id": dispatch_id,
        "op": "parallel_delegate",
        "issuer": issuer,
        "agents": agent_list,
        "prompt": prompt,
        "status": "done",
        "artifact_ids": artifact_ids,
        "started_at": _utc_now(),
        "ended_at": _utc_now(),
        "topic_category": _topic_category_meta(run_meta),
    }
    if trimmed:
        ledger_entry["trimmed_agents"] = trimmed
        ledger_entry["fanout_cap"] = dispatch_max_fanout()
    append_dispatch_ledger(run_meta, ledger_entry)
    _run_pre_post_dispatch_hooks(
        event="post_dispatch",
        run_meta=run_meta,
        folder=folder,
        dispatch_id=dispatch_id,
        dispatch_op="parallel_delegate",
        dispatch_agents=agent_list,
        prompt=prompt,
        human_turn=human_turn,
        on_event=on_event,
    )
    _emit_dispatch_events(
        on_event,
        "dispatch_done",
        {"dispatch_id": dispatch_id, "status": "done", **meta},
    )
    return replies, meta


def run_synthesize_dispatch(
    *,
    topic: str,
    messages: list[Any],
    run_meta: dict[str, Any],
    folder: Path,
    lead_agent: str,
    artifact_ids: list[str],
    permissions: dict | None,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
    human_turn: int = 1,
    issuer: str = "human",
) -> tuple[list[Any], dict[str, Any]]:
    """Lead agent synthesizes prior dispatch artifacts (Fable Plan pattern)."""
    dispatch_id = next_dispatch_id(run_meta)
    lead = lead_agent.strip().lower()
    arts = run_meta.get("artifacts") or []
    summaries: list[str] = []
    for art in arts:
        if not isinstance(art, dict):
            continue
        if art.get("id") in artifact_ids:
            summaries.append(f"- {art.get('id')} ({art.get('producer')}): {(art.get('summary') or '')[:200]}")
    synth_prompt = (
        "[DISPATCH synthesize]\n"
        "아래 scoped worker artifact들을 종합해 한 건의 실행 가능한 요약을 제시하세요.\n" + "\n".join(summaries[:10])
    )
    plan_md, _ = _session_context(folder)
    _emit_dispatch_events(
        on_event,
        "dispatch_start",
        {"dispatch_id": dispatch_id, "op": "synthesize", "agents": [lead]},
    )
    msg = _call_one_agent(
        lead,  # type: ignore[arg-type]
        topic=topic,
        thread=messages,
        parallel_round=1,
        permissions=permissions,
        review_mode=False,
        review_advocate=None,
        plan_md=plan_md,
        run_meta=run_meta,
        on_event=on_event,
        extra_follow_up=synth_prompt,
    )
    peer = ChatMessage(
        role="system",
        agent=None,
        content=f"[dispatch synthesize · {lead}]\n{(msg.content or '')[:500]}",
        visibility="peer",
        parallel_round=1,
    )
    meta = {"dispatch_id": dispatch_id, "op": "synthesize", "lead": lead}
    append_dispatch_ledger(
        run_meta,
        {
            "id": dispatch_id,
            "op": "synthesize",
            "issuer": issuer,
            "agents": [lead],
            "prompt": synth_prompt[:500],
            "status": "done",
            "artifact_ids": list(artifact_ids),
            "started_at": _utc_now(),
            "ended_at": _utc_now(),
            "topic_category": _topic_category_meta(run_meta),
        },
    )
    _emit_dispatch_events(
        on_event,
        "dispatch_done",
        {"dispatch_id": dispatch_id, "status": "done", **meta},
    )
    return [msg, peer], meta


def try_dispatch_turn(
    *,
    body: str,
    topic: str,
    messages: list[Any],
    run_meta: dict[str, Any],
    folder: Path,
    permissions: dict | None,
    on_event: Callable[[str, dict[str, Any]], None] | None,
    clarifier_questions: list[str] | None,
    human_turn: int,
) -> list[Any] | None:
    if clarifier_questions:
        return None
    spec = parse_dispatch_from_message(body)
    if not spec:
        return None
    if spec.op == "single_delegate":
        replies, _ = run_single_delegate(
            topic=topic,
            messages=messages,
            run_meta=run_meta,
            folder=folder,
            agent=spec.agents[0],
            prompt=spec.prompt,
            permissions=permissions,
            on_event=on_event,
            human_turn=human_turn,
        )
        return replies
    replies, _ = run_parallel_delegate(
        topic=topic,
        messages=messages,
        run_meta=run_meta,
        folder=folder,
        agents=list(spec.agents),
        prompt=spec.prompt,
        permissions=permissions,
        on_event=on_event,
        human_turn=human_turn,
        trimmed_agents=list(spec.trimmed_agents),
    )
    return replies


def dispatch_run_meta_patch(run_meta: dict[str, Any]) -> dict[str, Any] | None:
    patch: dict[str, Any] = {}
    if run_meta.get("last_delegate"):
        patch["last_delegate"] = run_meta.get("last_delegate")
    if run_meta.get("dispatch_ledger"):
        patch["dispatch_ledger"] = list(run_meta.get("dispatch_ledger") or [])
    if run_meta.get("dispatch_intents"):
        patch["dispatch_intents"] = list(run_meta.get("dispatch_intents") or [])
    if run_meta.get("artifacts"):
        patch["artifacts"] = list(run_meta.get("artifacts") or [])
    if run_meta.get("hook_runs"):
        patch["hook_runs"] = list(run_meta.get("hook_runs") or [])
    manifest = run_meta.get("agent_hooks_manifest")
    if manifest:
        patch["agent_hooks_manifest"] = dict(manifest)
    for key in ("turn_policy", "turn_kind", "room_preset"):
        if run_meta.get(key) is not None:
            patch[key] = run_meta.get(key)
    return patch or None
