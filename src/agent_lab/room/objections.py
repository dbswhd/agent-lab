"""Envelope BLOCK/CHALLENGE registry in run.json (Phase E — hard gates)."""

from __future__ import annotations

import os
import re
import uuid
from typing import Any, Literal

from agent_lab.time_utils import utc_now_iso as _now
from agent_lab.plan.actions import PlanActionKind, parse_action_key
from agent_lab.run.state import RunStateLike

from agent_lab.core.exceptions import ObjectionBlocksExecute
from agent_lab.core.objections import (
    HARVEST_ACTS,
    RUN_OBJECTIONS_KEY,
    list_objections,
    normalize_objection,
)

ObjectionStatus = Literal["open", "resolved_accepted", "resolved_wontfix"]
ResolveVerdict = Literal["accepted", "wontfix"]

_AGENT_IDS = frozenset({"cursor", "codex", "claude"})
_PLAN_ACTION_REF = re.compile(
    r"^(?:plan_action|plan-action|action)[:#]?\s*(\d+)$",
    re.I,
)
_TASK_ID_REF = re.compile(r"^(t-[a-f0-9]{6,})$", re.I)


def discuss_objections_enabled() -> bool:
    """``AGENT_LAB_DISCUSS_OBJECTIONS`` — discuss 모드 CHALLENGE/BLOCK도 상태로 등록 (기본 on)."""
    raw = (os.getenv("AGENT_LAB_DISCUSS_OBJECTIONS") or "").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _new_objection_id() -> str:
    return f"obj-{uuid.uuid4().hex[:10]}"


def write_objections(run_meta: RunStateLike, rows: list[dict[str, Any]]) -> None:
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(
        run_meta,
        **{RUN_OBJECTIONS_KEY: [normalize_objection(o) for o in rows]},
    )


def open_objections(run_meta: RunStateLike | None) -> list[dict[str, Any]]:
    return [o for o in list_objections(run_meta) if o.get("status") == "open"]


def _parse_plan_target(
    refs: list[str],
) -> tuple[int | None, PlanActionKind | None]:
    for ref in refs:
        text = str(ref).strip()
        if not text:
            continue
        parsed = parse_action_key(text)
        if parsed:
            return parsed[1], parsed[0]
        m = _PLAN_ACTION_REF.match(text)
        if m:
            return int(m.group(1)), None
        if text.isdigit():
            return int(text), "now"
    return None, None


def _parse_task_id(refs: list[str]) -> str | None:
    for ref in refs:
        text = str(ref).strip()
        if text.startswith("t-") and _TASK_ID_REF.match(text):
            return text
    return None


def _objection_fingerprint(
    *,
    from_agent: str,
    act: str,
    body: str,
    target_ref: str | None,
    task_id: str | None,
    plan_action_index: int | None,
) -> tuple:
    return (
        from_agent,
        act,
        body[:200],
        target_ref or "",
        task_id or "",
        plan_action_index,
    )


def append_objection(
    run_meta: RunStateLike,
    *,
    from_agent: str,
    act: str,
    body: str,
    human_turn: int,
    refs: list[str] | None = None,
    parallel_round: int | None = None,
    mode: str = "plan",
) -> dict[str, Any] | None:
    from_a = str(from_agent or "").strip().lower()
    if from_a not in _AGENT_IDS:
        return None
    act_u = str(act or "BLOCK").strip().upper()
    if act_u not in HARVEST_ACTS:
        return None
    text = (body or "").strip()
    if not text:
        return None
    ref_list = [str(r).strip() for r in (refs or []) if str(r).strip()]
    plan_idx, plan_kind = _parse_plan_target(ref_list)
    task_id = _parse_task_id(ref_list)
    target_ref = None
    if plan_idx is not None:
        target_ref = f"plan_action:{plan_idx}"
    elif task_id:
        target_ref = f"task:{task_id}"

    fp = _objection_fingerprint(
        from_agent=from_a,
        act=act_u,
        body=text,
        target_ref=target_ref,
        task_id=task_id,
        plan_action_index=plan_idx,
    )
    rows = list_objections(run_meta)
    # 같은 fingerprint면 status 무관 dedupe — endorse로 해소된 discuss CHALLENGE가
    # 턴 종료 재수확에서 다시 open으로 살아나면 합의 게이트가 교착한다.
    for existing in rows[-30:]:
        if (
            _objection_fingerprint(
                from_agent=str(existing.get("from") or ""),
                act=str(existing.get("act") or ""),
                body=str(existing.get("body") or ""),
                target_ref=existing.get("target_ref"),
                task_id=existing.get("task_id"),
                plan_action_index=existing.get("plan_action_index"),
            )
            == fp
        ):
            return existing

    row = normalize_objection(
        {
            "from": from_a,
            "act": act_u,
            "body": text,
            "status": "open",
            "turn": human_turn,
            "target_ref": target_ref,
            "task_id": task_id,
            "plan_action_index": plan_idx,
            "plan_action_kind": plan_kind,
            "parallel_round": parallel_round,
            "mode": mode,
        }
    )
    rows.append(row)
    write_objections(run_meta, rows)
    return row


def harvest_objections_from_turn(
    run_meta: RunStateLike,
    messages: list[Any],
    *,
    human_turn: int,
    mode: str = "discuss",
) -> list[dict[str, Any]]:
    """Harvest BLOCK/CHALLENGE envelopes from the current human turn.

    plan 모드는 항상, discuss 등 다른 모드는 ``AGENT_LAB_DISCUSS_OBJECTIONS``(기본 on)일 때
    수확한다 — 충돌이 파싱만 되고 증발하지 않고 상태(run.json)에 남는다 (P3).
    """
    if mode != "plan" and not discuss_objections_enabled():
        return []
    from agent_lab.agent.envelope import envelope_act, parse_agent_response

    last_user = -1
    for i, m in enumerate(messages):
        if getattr(m, "role", None) == "user":
            last_user = i
    turn = messages[last_user + 1 :] if last_user >= 0 else messages
    created: list[dict[str, Any]] = []
    for m in turn:
        if getattr(m, "role", None) != "agent":
            continue
        agent = str(getattr(m, "agent", "") or "").strip().lower()
        if agent not in _AGENT_IDS:
            continue
        env = getattr(m, "envelope", None)
        if env is not None and hasattr(env, "to_dict"):
            env = env.to_dict()
        if not isinstance(env, dict):
            parsed = parse_agent_response(getattr(m, "content", "") or "")
            env = parsed.envelope.to_dict() if parsed.envelope else None
        if not env:
            continue
        act = envelope_act(env)
        if act not in HARVEST_ACTS:
            continue
        refs = [str(r) for r in (env.get("refs") or []) if str(r).strip()]
        body = str(env.get("message") or getattr(m, "content", "") or "").strip()
        row = append_objection(
            run_meta,
            from_agent=agent,
            act=act or "BLOCK",
            body=body,
            human_turn=human_turn,
            refs=refs,
            parallel_round=getattr(m, "parallel_round", None),
            mode=mode,
        )
        if row and row not in created:
            created.append(row)
    return created


def resolve_objections_on_endorse(
    run_meta: RunStateLike,
    agent: str,
    *,
    human_turn: int | None = None,
    resolution: str = "challenger_endorsed_anchor",
) -> list[dict[str, Any]]:
    """Endorse 직후 본인이 연 discuss CHALLENGE를 자동 해소 (P3 필수 동반).

    도전자가 앵커를 ENDORSE했다 = 충돌이 도전자를 만족시키는 쪽으로 끝났다.
    이게 없으면 open-objections 합의 게이트가 모든 discuss 세션을 교착시킨다.
    BLOCK은 제외 — Human 해소 경로 유지.
    """
    agent_l = str(agent or "").strip().lower()
    if not run_meta or agent_l not in _AGENT_IDS:
        return []
    rows = list_objections(run_meta)
    resolved: list[dict[str, Any]] = []
    for row in rows:
        if row.get("status") != "open":
            continue
        if row.get("act") != "CHALLENGE":
            continue
        if str(row.get("mode") or "plan") == "plan":
            continue
        if str(row.get("from") or "").lower() != agent_l:
            continue
        row["status"] = "resolved_accepted"
        row["resolved_at"] = _now()
        row["resolved_by"] = agent_l
        row["resolution"] = resolution
        resolved.append(row)
    if not resolved:
        return []
    write_objections(run_meta, rows)
    for row in resolved:
        if row.get("task_id"):
            _unblock_task_if_no_open_challenge(run_meta, str(row["task_id"]))
    return resolved


def apply_challenge_task_blocks(run_meta: RunStateLike) -> int:
    """Mark tasks blocked when an open CHALLENGE references them."""
    from agent_lab.room.tasks import list_tasks, write_tasks

    open_ch = [o for o in open_objections(run_meta) if o.get("act") == "CHALLENGE" and o.get("task_id")]
    if not open_ch:
        return 0
    task_ids = {str(o["task_id"]) for o in open_ch if o.get("task_id")}
    tasks = list_tasks(run_meta)
    changed = 0
    for task in tasks:
        if task.get("id") not in task_ids:
            continue
        if task.get("status") in ("completed", "cancelled"):
            continue
        if task.get("status") != "blocked":
            task["status"] = "blocked"
            task["updated_at"] = _now()
            changed += 1
    if changed:
        write_tasks(run_meta, tasks)
    return changed


def resolve_objection(
    run_meta: RunStateLike,
    objection_id: str,
    *,
    verdict: ResolveVerdict,
    note: str = "",
    resolved_by: str = "human",
) -> dict[str, Any]:
    rows = list_objections(run_meta)
    oid = str(objection_id or "").strip()
    for row in rows:
        if str(row.get("id")) != oid:
            continue
        if row.get("status") != "open":
            raise ValueError(f"objection not open: {oid}")
        row["status"] = "resolved_accepted" if verdict == "accepted" else "resolved_wontfix"
        row["resolved_at"] = _now()
        row["resolved_by"] = resolved_by
        if note.strip():
            row["resolve_note"] = note.strip()[:500]
        write_objections(run_meta, rows)
        if row.get("task_id") and verdict == "accepted":
            _unblock_task_if_no_open_challenge(run_meta, str(row["task_id"]))
        return row
    raise ValueError(f"objection not found: {oid}")


def _unblock_task_if_no_open_challenge(run_meta: RunStateLike, task_id: str) -> None:
    from agent_lab.room.tasks import list_tasks, write_tasks

    still = any(
        o.get("status") == "open" and o.get("act") == "CHALLENGE" and o.get("task_id") == task_id
        for o in list_objections(run_meta)
    )
    if still:
        return
    tasks = list_tasks(run_meta)
    for task in tasks:
        if task.get("id") == task_id and task.get("status") == "blocked":
            task["status"] = "pending"
            task["updated_at"] = _now()
    write_tasks(run_meta, tasks)


def _action_matches_objection(
    obj: dict[str, Any],
    action_index: int,
    action_kind: PlanActionKind | None,
) -> bool:
    if obj.get("act") != "BLOCK":
        return False
    if obj.get("status") != "open":
        return False
    idx = obj.get("plan_action_index")
    if idx is not None and int(idx) == action_index:
        kind = obj.get("plan_action_kind")
        if kind and action_kind and kind != action_kind:
            return False
        return True
    target = str(obj.get("target_ref") or "")
    if target.startswith("plan_action:"):
        try:
            return int(target.split(":", 1)[1]) == action_index
        except ValueError:
            return False
    return False


def execute_block_reason_for_action(
    run_meta: RunStateLike | None,
    action_index: int,
    action_kind: PlanActionKind | None = None,
) -> str | None:
    """Return human-readable block reason for dry-run, or None."""
    blocking = [o for o in open_objections(run_meta) if _action_matches_objection(o, action_index, action_kind)]
    if not blocking:
        return None
    parts = [f"{o.get('from')} BLOCK (#{o.get('id', '?')[:8]}): {(o.get('body') or '')[:80]}" for o in blocking[:3]]
    return "미해결 이의(BLOCK)로 plan 실행을 할 수 없습니다 — 작업 바에서 이의를 해소하세요. " + " · ".join(parts)


def assert_execute_allowed(
    run_meta: RunStateLike | None,
    action_index: int,
    action_kind: PlanActionKind | None = None,
) -> None:
    reason = execute_block_reason_for_action(run_meta, action_index, action_kind)
    if reason:
        blocking = [o for o in open_objections(run_meta) if _action_matches_objection(o, action_index, action_kind)]
        raise ObjectionBlocksExecute(reason, objections=blocking)


def consensus_open_objection_blockers(run_meta: RunStateLike | None) -> list[str]:
    return [f"{o.get('from')}:{o.get('act')}:{o.get('id')}" for o in open_objections(run_meta)]


def objections_public_payload(run_meta: RunStateLike | None) -> dict[str, Any]:
    rows = list_objections(run_meta)
    open_rows = [o for o in rows if o.get("status") == "open"]
    return {
        "objections": rows[-50:],
        "open_objections": open_rows,
        "open_objection_count": len(open_rows),
    }


def build_objection_block(run_meta: RunStateLike | None, agent: str) -> str:
    agent_l = str(agent or "").strip().lower()
    relevant = [o for o in open_objections(run_meta) if str(o.get("from") or "").lower() != agent_l]
    if not relevant:
        return ""
    lines = ["[미해결 이의 — BLOCK/CHALLENGE]", ""]
    for o in relevant[:6]:
        ref = o.get("target_ref") or o.get("task_id") or "—"
        lines.append(f"- {o.get('from')} {o.get('act')} → {ref}: {(o.get('body') or '')[:120]}")
    lines.append("")
    lines.append("해소: Human이 작업 바에서 accepted/wontfix, 또는 AMEND envelope.")
    return "\n".join(lines)


def build_challenge_owner_block(run_meta: RunStateLike | None, agent: str) -> str:
    """E3: task owner must AMEND or justify when CHALLENGE is open."""
    from agent_lab.room.tasks import list_tasks

    agent_l = str(agent or "").strip().lower()
    challenged_ids = {
        str(o.get("task_id")) for o in open_objections(run_meta) if o.get("act") == "CHALLENGE" and o.get("task_id")
    }
    if not challenged_ids:
        return ""
    owned: list[dict[str, Any]] = []
    for task in list_tasks(run_meta):
        if task.get("id") not in challenged_ids:
            continue
        owner = str(task.get("owner_agent") or "").strip().lower()
        if owner and owner != agent_l:
            continue
        if task.get("status") == "blocked" or owner == agent_l:
            owned.append(task)
    if not owned:
        return ""
    lines = ["[CHALLENGE · 반드시 응답]", ""]
    for task in owned[:4]:
        oid = next(
            (o for o in open_objections(run_meta) if o.get("task_id") == task.get("id")),
            {},
        )
        lines.append(f"- task {task.get('id')}: {(task.get('title') or '')[:80]}")
        if oid.get("body"):
            lines.append(f"  challenge: {(oid.get('body') or '')[:160]}")
    lines.append("")
    lines.append("envelope `AMEND` + refs에 task id, 또는 본문에서 근거·수정안을 제시하세요.")
    return "\n".join(lines)
