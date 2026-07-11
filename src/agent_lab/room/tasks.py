"""Shared task list for multi-agent room sessions (Phase 1 — team coordination)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Literal

from agent_lab.time_utils import utc_now_iso as _now
from agent_lab.run.state import RunStateLike

TaskStatus = Literal["pending", "in_progress", "completed", "cancelled", "blocked"]

_TASK_STATUSES: frozenset[str] = frozenset({"pending", "in_progress", "completed", "cancelled", "blocked"})

_PROPOSED_RE = re.compile(r"\[PROPOSED:\s*([^\]]+)\]", re.I)

RUN_TASKS_KEY = "tasks"
RUN_TEAM_LEAD_KEY = "team_lead"
RUN_PLAN_PROVENANCE_KEY = "plan_provenance"
DEFAULT_TEAM_LEAD = "cursor"
MAX_CLAIMS_PER_AGENT_PER_TURN = 1


def _new_task_id() -> str:
    return f"t-{uuid.uuid4().hex[:10]}"


def normalize_task(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a task dict with required keys and sane defaults."""
    tid = str(raw.get("id") or _new_task_id()).strip() or _new_task_id()
    status = str(raw.get("status") or "pending").strip().lower()
    if status not in _TASK_STATUSES:
        status = "pending"
    depends = raw.get("depends_on") or []
    if not isinstance(depends, list):
        depends = []
    depends_on = [str(d).strip() for d in depends if str(d).strip()]
    refs = raw.get("artifact_refs") or []
    if not isinstance(refs, list):
        refs = []
    artifact_refs = [str(r).strip() for r in refs if str(r).strip()]
    out: dict[str, Any] = {
        "id": tid,
        "title": str(raw.get("title") or "").strip()[:500],
        "status": status,
        "owner_agent": (str(raw.get("owner_agent")).strip() if raw.get("owner_agent") else None),
        "depends_on": depends_on,
        "artifact_refs": artifact_refs,
        "source": str(raw.get("source") or "manual").strip()[:80],
        "created_at": str(raw.get("created_at") or _now()),
        "updated_at": str(raw.get("updated_at") or _now()),
    }
    if raw.get("human_turn") is not None:
        try:
            out["human_turn"] = int(raw["human_turn"])
        except (TypeError, ValueError):
            pass
    if raw.get("parallel_round") is not None:
        try:
            out["parallel_round"] = int(raw["parallel_round"])
        except (TypeError, ValueError):
            pass
    if raw.get("plan_action_index") is not None:
        try:
            out["plan_action_index"] = int(raw["plan_action_index"])
        except (TypeError, ValueError):
            pass
    paid = raw.get("plan_action_id")
    if paid:
        out["plan_action_id"] = str(paid).strip()[:120]
    end = raw.get("endorsements")
    if isinstance(end, dict):
        out["endorsements"] = {
            str(k).strip().lower(): str(v).strip() for k, v in end.items() if str(k).strip() and str(v).strip()
        }
    return out


def list_tasks(run_meta: RunStateLike | None) -> list[dict[str, Any]]:
    if not run_meta:
        return []
    raw = run_meta.get(RUN_TASKS_KEY)
    if not isinstance(raw, list):
        return []
    return [normalize_task(t) for t in raw if isinstance(t, dict)]


def write_tasks(run_meta: RunStateLike, tasks: list[dict[str, Any]]) -> None:
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(run_meta, **{RUN_TASKS_KEY: [normalize_task(t) for t in tasks]})


def team_lead(run_meta: RunStateLike | None) -> str:
    if not run_meta:
        return DEFAULT_TEAM_LEAD
    lead = str(run_meta.get(RUN_TEAM_LEAD_KEY) or "").strip().lower()
    return lead or DEFAULT_TEAM_LEAD


def ensure_team_lead(run_meta: RunStateLike) -> str:
    from agent_lab.run.meta import stamp_run_meta

    lead = team_lead(run_meta)
    stamp_run_meta(run_meta, **{RUN_TEAM_LEAD_KEY: lead})
    return lead


def _task_by_id(tasks: list[dict[str, Any]], task_id: str) -> dict[str, Any] | None:
    for t in tasks:
        if t.get("id") == task_id:
            return t
    return None


def _deps_satisfied(task: dict[str, Any], tasks: list[dict[str, Any]]) -> bool:
    for dep_id in task.get("depends_on") or []:
        dep = _task_by_id(tasks, dep_id)
        if dep is None or dep.get("status") != "completed":
            return False
    return True


def claimable_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in tasks:
        if t.get("status") != "pending":
            continue
        if t.get("owner_agent"):
            continue
        if _deps_satisfied(t, tasks):
            out.append(t)
    return out


def claim_task(
    run_meta: RunStateLike,
    task_id: str,
    agent: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Assign pending task to agent. Single-process orchestrator — no file lock."""
    tasks = list_tasks(run_meta)
    task = _task_by_id(tasks, task_id)
    if task is None:
        raise ValueError(f"task not found: {task_id}")
    status = task.get("status")
    if status == "completed":
        raise ValueError("task already completed")
    if status == "in_progress" and task.get("owner_agent") and not force:
        owner = task.get("owner_agent")
        if owner != agent:
            raise ValueError(f"task owned by {owner}")
    if not _deps_satisfied(task, tasks):
        raise ValueError("task dependencies not completed")
    if status != "pending" and status != "in_progress":
        raise ValueError(f"cannot claim task in status {status}")
    task["status"] = "in_progress"
    task["owner_agent"] = agent.strip().lower()
    task["updated_at"] = _now()
    write_tasks(run_meta, tasks)
    return dict(task)


def _latest_execution_for_task(
    run_meta: RunStateLike,
    task: dict[str, Any],
) -> dict[str, Any] | None:
    """Most recent execution row linked to the task's plan action."""
    idx = task.get("plan_action_index")
    paid = task.get("plan_action_id")
    if idx is None and not paid:
        return None
    rows = run_meta.get("executions")
    if not isinstance(rows, list):
        return None
    latest: dict[str, Any] | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        match = False
        if idx is not None and row.get("action_index") == idx:
            match = True
        if paid and row.get("action_id") == paid:
            match = True
        if match:
            latest = row
    return latest


def _execution_by_id(run_meta: RunStateLike, execution_id: str) -> dict[str, Any] | None:
    for row in run_meta.get("executions") or []:
        if isinstance(row, dict) and str(row.get("id") or "") == execution_id:
            return row
    return None


def task_complete_block_reason(
    run_meta: RunStateLike,
    task: dict[str, Any],
) -> str | None:
    """Block manual complete when plan execute is not verified for this action."""
    from agent_lab.runtime.invoke_execute import execution_allows_task_complete

    if task.get("plan_action_index") is None and not task.get("plan_action_id"):
        pass
    else:
        ex = _latest_execution_for_task(run_meta, task)
        if ex:
            status = str(ex.get("status") or "")
            if status == "pending_approval":
                return "plan 실행 승인 대기 중 — dry-run 승인 후 완료하세요."
            if status == "review_required":
                return "plan 실행 검증(PDF 등) 미완료 — 승인·검증 후 완료하세요."
            if not execution_allows_task_complete(ex):
                return "plan 실행이 완료·검증되지 않았습니다 — 승인 후 완료하세요."

    for ref in task.get("artifact_refs") or []:
        r = str(ref).strip()
        if not r.startswith("execution:"):
            continue
        ex_id = r.split(":", 1)[1].strip()
        if not ex_id:
            continue
        ex = _execution_by_id(run_meta, ex_id)
        if ex and not execution_allows_task_complete(ex):
            return f"연결된 실행({ex_id}) 검증 미완료 — execute 승인·검증 후 완료하세요."
    return None


def complete_task(
    run_meta: RunStateLike,
    task_id: str,
    *,
    artifact_refs: list[str] | None = None,
) -> dict[str, Any]:
    tasks = list_tasks(run_meta)
    task = _task_by_id(tasks, task_id)
    if task is None:
        raise ValueError(f"task not found: {task_id}")
    if task.get("status") == "blocked":
        raise ValueError("CHALLENGE로 차단된 작업입니다 — 이의를 해소하거나 AMEND 후 다시 진행하세요.")
    block = task_complete_block_reason(run_meta, task)
    if block:
        raise ValueError(block)
    from agent_lab.runtime.policy import PolicyEngine

    folder_raw = run_meta.get("_session_folder")
    session_folder = Path(str(folder_raw)) if folder_raw and str(folder_raw).strip() else None
    policy = PolicyEngine.check_task_completed(
        run_meta,
        task,
        session_folder=session_folder,
        session_id=str(run_meta.get("_session_id") or ""),
    )
    if policy.blocked:
        raise ValueError(policy.reason or "task_completed hook blocked")
    task["status"] = "completed"
    task["updated_at"] = _now()
    if artifact_refs:
        existing = list(task.get("artifact_refs") or [])
        for ref in artifact_refs:
            r = ref.strip()
            if r and r not in existing:
                existing.append(r)
        task["artifact_refs"] = existing
    write_tasks(run_meta, tasks)
    return dict(task)


def add_task(
    run_meta: RunStateLike,
    title: str,
    *,
    source: str = "manual",
    owner_agent: str | None = None,
    depends_on: list[str] | None = None,
    human_turn: int | None = None,
    parallel_round: int | None = None,
    status: TaskStatus = "pending",
) -> dict[str, Any]:
    tasks = list_tasks(run_meta)
    title_norm = title.strip()
    if not title_norm:
        raise ValueError("task title required")
    key = title_norm.lower()
    for t in tasks:
        if str(t.get("title", "")).strip().lower() == key and t.get("status") in ("pending", "in_progress"):
            return t
    task = normalize_task(
        {
            "id": _new_task_id(),
            "title": title_norm,
            "status": status,
            "owner_agent": owner_agent,
            "depends_on": depends_on or [],
            "source": source,
            "human_turn": human_turn,
            "parallel_round": parallel_round,
        }
    )
    # 제안자는 자기 작업에 암묵 동의 — 별도 ENDORSE refs 없이도 합의 정족수에 포함.
    # (Human이 "동의해 주세요"를 직접 칠 필요를 없앤다.)
    if owner_agent and str(owner_agent).strip():
        record_task_endorsement(task, str(owner_agent))
    tasks.append(task)
    write_tasks(run_meta, tasks)
    return task


def extract_proposed_titles(text: str) -> list[str]:
    found: list[str] = []
    for match in _PROPOSED_RE.finditer(text or ""):
        item = match.group(1).strip()
        if item and item not in found:
            found.append(item[:200])
    return found


def sync_tasks_from_messages(
    run_meta: RunStateLike,
    messages: list[Any],
    *,
    human_turn: int,
) -> list[dict[str, Any]]:
    """Create pending tasks from [PROPOSED:] tags in the latest human turn."""
    from agent_lab.plan.pending import max_tasks_per_turn

    cap = max_tasks_per_turn()
    last_user = -1
    for i, m in enumerate(messages):
        if getattr(m, "role", None) == "user":
            last_user = i
    turn = messages[last_user + 1 :] if last_user >= 0 else messages
    created: list[dict[str, Any]] = []
    seen_ids = {t["id"] for t in list_tasks(run_meta)}
    for m in turn:
        if len(created) >= cap:
            break
        if getattr(m, "role", None) != "agent":
            continue
        pr = getattr(m, "parallel_round", None) or 1
        proposer = str(getattr(m, "agent", "") or "").strip().lower() or None
        for title in extract_proposed_titles(getattr(m, "content", "") or ""):
            if len(created) >= cap:
                break
            task = add_task(
                run_meta,
                title,
                source="proposed",
                owner_agent=proposer,
                human_turn=human_turn,
                parallel_round=int(pr),
            )
            tid = task.get("id")
            if tid and tid not in seen_ids:
                seen_ids.add(tid)
                created.append(task)
    return created


def sync_tasks_from_turn_state(run_meta: RunStateLike) -> list[dict[str, Any]]:
    """Mirror turn_state.open_issues into pending tasks when not duplicate."""
    from agent_lab.plan.pending import max_tasks_per_turn

    cap = max_tasks_per_turn()
    ts = run_meta.get("turn_state")
    if not isinstance(ts, dict):
        return []
    issues = ts.get("open_issues")
    if not isinstance(issues, list):
        return []
    created: list[dict[str, Any]] = []
    for item in issues:
        if len(created) >= cap:
            break
        title = str(item).strip()
        if not title:
            continue
        task = add_task(run_meta, title, source="turn_state")
        if task.get("id"):
            created.append(task)
    return created


def mark_tasks_in_progress_for_execution(
    run_meta: RunStateLike,
    *,
    action_index: int | None = None,
    action_id: str | None = None,
    execution_id: str | None = None,
) -> list[dict[str, Any]]:
    """Link plan dry-run start → task in_progress (Sprint B)."""
    updated: list[dict[str, Any]] = []
    tasks = list_tasks(run_meta)
    for task in tasks:
        if task.get("status") in ("completed", "cancelled"):
            continue
        match = False
        if action_index is not None and task.get("plan_action_index") == action_index:
            match = True
        if action_id and task.get("plan_action_id") == action_id:
            match = True
        if not match:
            continue
        if task.get("status") == "pending":
            task["status"] = "in_progress"
        task["updated_at"] = _now()
        if execution_id:
            refs = list(task.get("artifact_refs") or [])
            ref = f"execution:{execution_id}"
            if ref not in refs:
                refs.append(ref)
            task["artifact_refs"] = refs
        updated.append(dict(task))
    if updated:
        write_tasks(run_meta, tasks)
    return updated


def revert_tasks_for_rejected_execution(
    run_meta: RunStateLike,
    *,
    action_index: int | None = None,
    action_id: str | None = None,
    execution_id: str | None = None,
) -> list[dict[str, Any]]:
    """Dry-run rejected → linked tasks back to pending."""
    reverted: list[dict[str, Any]] = []
    tasks = list_tasks(run_meta)
    for task in tasks:
        if task.get("status") != "in_progress":
            continue
        match = False
        if action_index is not None and task.get("plan_action_index") == action_index:
            match = True
        if action_id and task.get("plan_action_id") == action_id:
            match = True
        if not match:
            continue
        task["status"] = "pending"
        task["updated_at"] = _now()
        if execution_id:
            refs = [r for r in (task.get("artifact_refs") or []) if r != f"execution:{execution_id}"]
            task["artifact_refs"] = refs
        reverted.append(dict(task))
    if reverted:
        write_tasks(run_meta, tasks)
    return reverted


def _title_matches_plan_action(title: str, what: str) -> bool:
    a = title.strip().lower()
    b = what.strip().lower()
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    return a[:48] == b[:48]


def sync_tasks_plan_links(run_meta: RunStateLike, plan_md: str) -> int:
    """Link open tasks to plan ## 지금 실행 actions by title similarity."""
    from agent_lab.plan.actions import parse_plan_actions

    actions = [a for a in parse_plan_actions(plan_md or "") if a.executable]
    if not actions:
        return 0
    tasks = list_tasks(run_meta)
    linked = 0
    for task in tasks:
        if task.get("status") in ("completed", "cancelled"):
            continue
        if task.get("plan_action_index") is not None:
            continue
        for action in actions:
            if _title_matches_plan_action(str(task.get("title") or ""), action.what):
                task["plan_action_index"] = action.index
                task["plan_action_id"] = action.action_id
                task["updated_at"] = _now()
                linked += 1
                break
    if linked:
        write_tasks(run_meta, tasks)
    return linked


def _task_matches_ref(task: dict[str, Any], ref: str) -> bool:
    ref_l = ref.strip().lower()
    if not ref_l:
        return False
    tid = str(task.get("id") or "").lower()
    title = str(task.get("title") or "").lower()
    paid = str(task.get("plan_action_id") or "").lower()
    if ref_l == tid or (title and (ref_l in title or title in ref_l)):
        return True
    if paid and (ref_l == paid or ref_l in paid):
        return True
    return False


def record_task_endorsement(task: dict[str, Any], agent: str) -> None:
    end = task.get("endorsements")
    if not isinstance(end, dict):
        end = {}
    end[str(agent).strip().lower()] = _now()
    task["endorsements"] = end
    task["updated_at"] = _now()


def harvest_task_endorsements(
    run_meta: RunStateLike,
    messages: list[Any],
    active_agents: list[str],
) -> int:
    """Count agent messages whose envelope ENDORSE/PASS refs open tasks."""
    from agent_lab.agent.envelope import envelope_act, parse_agent_response

    tasks = list_tasks(run_meta)
    if not tasks:
        return 0
    active = {a.strip().lower() for a in active_agents if str(a).strip()}
    touched = 0
    for m in messages:
        if getattr(m, "role", None) != "agent":
            continue
        agent = str(getattr(m, "agent", "") or "").strip().lower()
        if agent not in active:
            continue
        env = getattr(m, "envelope", None)
        if env is None:
            parsed = parse_agent_response(getattr(m, "content", "") or "")
            env = parsed.envelope
        act = envelope_act(env)
        if act not in ("ENDORSE", "PASS"):
            continue
        refs: list[str] = []
        if isinstance(env, dict):
            refs = [str(r) for r in (env.get("refs") or []) if str(r).strip()]
        elif env is not None:
            refs = [str(r) for r in (getattr(env, "refs", None) or []) if str(r).strip()]
        if not refs:
            continue
        for task in tasks:
            if task.get("status") in ("completed", "cancelled"):
                continue
            for ref in refs:
                if _task_matches_ref(task, ref):
                    record_task_endorsement(task, agent)
                    touched += 1
                    break
    if touched:
        write_tasks(run_meta, tasks)
    return touched


def open_tasks_for_consensus(run_meta: RunStateLike | None) -> list[dict[str, Any]]:
    return [t for t in list_tasks(run_meta) if t.get("status") in ("pending", "in_progress")]


def build_consensus_gate(
    run_meta: RunStateLike | None,
    agent_pool: list[str],
) -> dict[str, Any]:
    """Structured consensus gate for UI (Phase B task bar)."""
    active = [str(a).strip().lower() for a in agent_pool if str(a).strip()]
    required = max(1, len(active) - 1) if active else 1
    blocked: list[dict[str, Any]] = []
    for task in open_tasks_for_consensus(run_meta):
        end = task.get("endorsements")
        if not isinstance(end, dict):
            end = {}
        count = len(end)
        if count < required:
            blocked.append(
                {
                    "id": str(task.get("id") or ""),
                    "title": str(task.get("title") or task.get("id") or "?"),
                    "endorsements": count,
                }
            )
    return {
        "required_endorsements": required,
        "active_agent_count": len(active) if active else 3,
        "blocked_tasks": blocked,
    }


def agents_missing_task_endorse(
    run_meta: RunStateLike | None,
    active_agents: list[str],
) -> list[str]:
    """Active agents who still owe an ENDORSE on at least one under-endorsed open task.

    Drives the auto ENDORSE round so the Human doesn't have to manually nudge the
    team — we re-prompt exactly the agents whose endorsement is missing.
    """
    open_tasks = open_tasks_for_consensus(run_meta)
    if not open_tasks:
        return []
    active = [a.strip().lower() for a in active_agents if str(a).strip()]
    if not active:
        return []
    min_endorsements = max(1, len(active) - 1)
    missing: list[str] = []
    for aid in active:
        for task in open_tasks:
            end = task.get("endorsements")
            if not isinstance(end, dict):
                end = {}
            if len(end) >= min_endorsements:
                continue
            if aid not in end:
                missing.append(aid)
                break
    return missing


def consensus_tasks_ready(
    run_meta: RunStateLike | None,
    active_agents: list[str],
) -> tuple[bool, list[str]]:
    """Open tasks need endorsements from a majority of active agents."""
    open_tasks = open_tasks_for_consensus(run_meta)
    if not open_tasks:
        return True, []
    active = [a.strip().lower() for a in active_agents if str(a).strip()]
    if not active:
        return True, []
    min_endorsements = max(1, len(active) - 1)
    blockers: list[str] = []
    for task in open_tasks:
        end = task.get("endorsements")
        if not isinstance(end, dict):
            end = {}
        if len(end) < min_endorsements:
            blockers.append(str(task.get("title") or task.get("id") or "?"))
    return len(blockers) == 0, blockers


def complete_tasks_for_execution(
    run_meta: RunStateLike,
    *,
    action_index: int | None = None,
    action_id: str | None = None,
    execution_id: str | None = None,
    execution: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Mark tasks linked to a plan action completed after Human approves execute."""
    if execution is not None:
        from agent_lab.runtime.invoke_execute import execution_allows_task_complete

        if not execution_allows_task_complete(execution):
            return []
    done: list[dict[str, Any]] = []
    for task in list_tasks(run_meta):
        if task.get("status") in ("completed", "cancelled"):
            continue
        match = False
        if action_index is not None and task.get("plan_action_index") == action_index:
            match = True
        if action_id and task.get("plan_action_id") == action_id:
            match = True
        if not match:
            continue
        refs = [f"execution:{execution_id}"] if execution_id else []
        done.append(complete_task(run_meta, str(task["id"]), artifact_refs=refs or None))
    return done


def sync_tasks_after_turn(
    run_meta: RunStateLike,
    messages: list[Any],
    *,
    human_turn: int,
    plan_md: str = "",
    mode: str = "discuss",
    synthesize: bool = False,
    consensus_mode: bool = False,
) -> dict[str, Any]:
    """Run after each room turn write: team lead default + task harvest."""
    from agent_lab.room.team_orchestration import is_discuss_only_turn
    from agent_lab.room.turn_policy import is_discuss_only_for_run_meta, turn_policy_enabled

    ensure_team_lead(run_meta)
    from_proposed = sync_tasks_from_messages(run_meta, messages, human_turn=human_turn)
    if turn_policy_enabled():
        discuss_only = is_discuss_only_for_run_meta(run_meta)
    else:
        discuss_only = is_discuss_only_turn(mode=mode, synthesize=synthesize, consensus_mode=consensus_mode)
    from_state = sync_tasks_from_turn_state(run_meta) if not discuss_only else []
    harvest_task_endorsements(
        run_meta,
        messages,
        [
            str(getattr(m, "agent", "") or "")
            for m in messages
            if getattr(m, "role", None) == "agent" and getattr(m, "agent", None)
        ],
    )
    linked = 0
    if not discuss_only and plan_md.strip():
        linked = sync_tasks_plan_links(run_meta, plan_md)
    return {
        "team_lead": team_lead(run_meta),
        "tasks": list_tasks(run_meta),
        "created_from_proposed": len(from_proposed),
        "created_from_turn_state": len(from_state),
        "plan_links": linked,
        "discuss_only": discuss_only,
    }


def tasks_public_payload(run_meta: RunStateLike | None) -> dict[str, Any]:
    tasks = list_tasks(run_meta)
    open_tasks = open_tasks_for_consensus(run_meta)
    agent_pool = (
        [str(a) for a in run_meta.get("agents") or []]
        if run_meta and isinstance(run_meta.get("agents"), list)
        else ["cursor", "codex", "claude"]
    )
    ready, blockers = consensus_tasks_ready(run_meta, agent_pool)
    consensus_gate = build_consensus_gate(run_meta, agent_pool)
    from agent_lab.plan.pending import max_tasks_per_turn

    from agent_lab.room.team_orchestration import turn_leads_map
    from agent_lab.room.mailbox import mailbox_public_payload
    from agent_lab.room.artifacts import artifacts_public_payload
    from agent_lab.room.objections import objections_public_payload

    return {
        "team_lead": team_lead(run_meta),
        "turn_leads": turn_leads_map(run_meta),
        "agents": agent_pool,
        **mailbox_public_payload(run_meta),
        **objections_public_payload(run_meta),
        **artifacts_public_payload(run_meta),
        "tasks": tasks,
        "claimable": claimable_tasks(tasks),
        "max_tasks_per_turn": max_tasks_per_turn(),
        "counts": {
            "pending": sum(1 for t in tasks if t.get("status") == "pending"),
            "in_progress": sum(1 for t in tasks if t.get("status") == "in_progress"),
            "completed": sum(1 for t in tasks if t.get("status") == "completed"),
        },
        "consensus_tasks_ready": ready,
        "consensus_task_blockers": blockers,
        "consensus_gate": consensus_gate,
        "open_task_count": len(open_tasks),
    }


def assign_tasks_to_agents(
    run_meta: RunStateLike,
    agents: list[str],
    *,
    max_per_agent: int = 2,
) -> list[dict[str, Any]]:
    """Lead-style assignment: round-robin claim on claimable pending tasks."""
    ensure_team_lead(run_meta)
    assigned: list[dict[str, Any]] = []
    pool = [a.strip().lower() for a in agents if str(a).strip()]
    lead = team_lead(run_meta)
    teammates = [a for a in pool if a != lead] or pool
    if not teammates:
        return assigned
    idx = 0
    for task in claimable_tasks(list_tasks(run_meta)):
        if len(assigned) >= len(teammates) * max_per_agent:
            break
        agent = teammates[idx % len(teammates)]
        idx += 1
        try:
            assigned.append(claim_task(run_meta, str(task["id"]), agent))
        except ValueError:
            continue
    return assigned


def build_team_task_block(
    run_meta: RunStateLike | None,
    agent_id: str,
) -> str:
    """Agent context: lead sees full board; teammates see owned + claimable."""
    if not run_meta:
        return ""
    tasks = list_tasks(run_meta)
    if not tasks:
        return ""
    aid = str(agent_id or "").strip().lower()
    lead = team_lead(run_meta)
    lines: list[str] = ["[팀 작업 보드]"]

    def _row(t: dict[str, Any]) -> str:
        owner = t.get("owner_agent") or "미배정"
        return f"- [{t.get('status')}] {t.get('title')} (@{owner})"

    if aid == lead:
        lines.append(f"역할: 팀 리드 — 전체 작업 조율·우선순위·합의 정리 (리드: {lead})")
        lines.append(
            "discuss: 동료 제안을 종합하고 claim·execute 분배를 조율 — 대형 패치는 plan execute·Human 승인 후."
        )
        for t in tasks:
            if t.get("status") == "cancelled":
                continue
            lines.append(_row(t))
        claimable = claimable_tasks(tasks)
        if claimable:
            lines.append("청구 가능(미배정 · 의존성 충족):")
            for t in claimable:
                lines.append(f"  · {t.get('title')}")
    else:
        mine = [t for t in tasks if t.get("owner_agent") == aid and t.get("status") in ("pending", "in_progress")]
        if mine:
            lines.append(f"내 담당 작업 ({aid}):")
            for t in mine:
                lines.append(_row(t))
        claimable = claimable_tasks(tasks)
        if claimable:
            lines.append("청구 가능 (envelope refs 또는 POST claim, 턴당 1건):")
            for t in claimable[:8]:
                lines.append(f"  · {t.get('title')} ({t.get('id')})")
        lines.append("teammate discuss: 전체 패치 구현 금지 — [PROPOSED:]·claim·검증 제안만.")
        if not mine and not claimable:
            return ""

    lines.append("discuss 턴: 작업 제안·분해만 — plan execute는 Human 승인 후 별도.")
    lines.append('동료에게 직접 메시지: envelope `MESSAGE` + `"to":"codex"` (+ optional `message`).')
    return "\n".join(lines)


def _task_ref_matches(task: dict[str, Any], ref: str) -> bool:
    ref_s = str(ref).strip()
    if not ref_s:
        return False
    tid = str(task.get("id") or "")
    title = str(task.get("title") or "").strip().lower()
    paid = str(task.get("plan_action_id") or "")
    if ref_s == tid or ref_s == paid:
        return True
    if title and ref_s.lower() == title:
        return True
    if title and ref_s.lower() in title:
        return True
    return False


def auto_claim_tasks_from_turn(
    run_meta: RunStateLike,
    messages: list[Any],
    *,
    lead_agent: str | None = None,
    max_per_agent: int = MAX_CLAIMS_PER_AGENT_PER_TURN,
) -> list[dict[str, Any]]:
    """Light auto-claim when envelope refs match an unassigned pending task."""
    lead = (lead_agent or team_lead(run_meta)).strip().lower()
    last_user = -1
    for i, m in enumerate(messages):
        if getattr(m, "role", None) == "user":
            last_user = i
    turn = messages[last_user + 1 :] if last_user >= 0 else messages
    claims_by_agent: dict[str, int] = {}
    claimed: list[dict[str, Any]] = []
    for m in turn:
        if getattr(m, "role", None) != "agent":
            continue
        agent = str(getattr(m, "agent", "") or "").strip().lower()
        if not agent or agent == lead:
            continue
        env = getattr(m, "envelope", None)
        if not isinstance(env, dict):
            continue
        refs = env.get("refs")
        if not isinstance(refs, list):
            continue
        if claims_by_agent.get(agent, 0) >= max_per_agent:
            continue
        for ref in refs:
            if claims_by_agent.get(agent, 0) >= max_per_agent:
                break
            ref_s = str(ref).strip()
            if not ref_s or ref_s.upper().startswith("L"):
                continue
            for task in claimable_tasks(list_tasks(run_meta)):
                if not _task_ref_matches(task, ref_s):
                    continue
                try:
                    claimed.append(claim_task(run_meta, str(task["id"]), agent))
                    claims_by_agent[agent] = claims_by_agent.get(agent, 0) + 1
                except ValueError:
                    pass
                break
    return claimed


def set_team_lead_agent(run_meta: RunStateLike, agent: str) -> str:
    from agent_lab.run.meta import stamp_run_meta

    lead = str(agent or "").strip().lower() or DEFAULT_TEAM_LEAD
    stamp_run_meta(run_meta, **{RUN_TEAM_LEAD_KEY: lead})
    return lead
