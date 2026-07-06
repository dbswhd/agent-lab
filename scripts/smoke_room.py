#!/usr/bin/env python3
"""Room regression smoke: validate sessions/_regression baselines + optional API health."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGRESSION = ROOT / "sessions" / "_regression"
EXAMPLES = ROOT / "sessions" / "_examples"
API = "http://127.0.0.1:8765"


def _execs(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in run.get("executions") or [] if isinstance(row, dict)]


def _has_worktree_meta(row: dict[str, Any]) -> bool:
    return all(row.get(k) for k in ("git_root", "base_branch", "exec_branch", "worktree_path"))


def _check_worktree_merge_ok(run: dict[str, Any]) -> bool:
    rows = _execs(run)
    return any(
        row.get("status") == "merged"
        and row.get("isolation_effective") == "worktree"
        and _has_worktree_meta(row)
        and isinstance(row.get("merge"), dict)
        and row["merge"].get("commit_sha")
        for row in rows
    )


def _check_worktree_reject(run: dict[str, Any]) -> bool:
    return any(row.get("status") == "rejected" and row.get("isolation_effective") == "worktree" for row in _execs(run))


def _check_worktree_unavailable(run: dict[str, Any]) -> bool:
    return any(
        row.get("status") == "blocked_isolation"
        and row.get("isolation_effective") == "block"
        and row.get("blocked_reason")
        for row in _execs(run)
    )


def _check_merge_conflict(run: dict[str, Any]) -> bool:
    return any(
        row.get("status") == "merge_conflict"
        and isinstance(row.get("merge"), dict)
        and row["merge"].get("status") == "conflict"
        and bool(row["merge"].get("conflict_files"))
        for row in _execs(run)
    )


def _check_apply(run: dict[str, Any]) -> bool:
    return any(
        row.get("isolation_effective") == "apply" and row.get("status") in {"completed", "review_required"}
        for row in _execs(run)
    )


def _check_snapshot_override(run: dict[str, Any]) -> bool:
    return any(
        row.get("isolation_effective") == "snapshot_override"
        and row.get("status") == "pending_approval"
        and row.get("isolation_override_by") == "human"
        for row in _execs(run)
    )


def _check_pre_execute_blocked(run: dict[str, Any]) -> bool:
    return any(
        row.get("status") == "blocked_isolation"
        and isinstance(row.get("pre_verify"), dict)
        and row["pre_verify"].get("blocked") is True
        for row in _execs(run)
    )


def _check_adversarial_gate_lgtm(run: dict[str, Any]) -> bool:
    return any(
        row.get("status") == "review_required"
        and isinstance(row.get("adversarial_note"), str)
        and bool(row["adversarial_note"].strip())
        and row.get("adversarial_source") == "mock"
        for row in _execs(run)
    )


def _check_execute_verify_loop(run: dict[str, Any]) -> bool:
    for row in _execs(run):
        if row.get("status") != "merged":
            continue
        verify_after_merge = row.get("verify_after_merge")
        if not isinstance(verify_after_merge, dict):
            continue
        oracle = verify_after_merge.get("oracle") or row.get("oracle")
        if not isinstance(oracle, dict):
            continue
        if verify_after_merge.get("status") != "passed":
            continue
        if verify_after_merge.get("source") != "mock_oracle":
            continue
        if oracle.get("verdict") != "pass":
            continue
        try:
            retries = int(row.get("verify_retries", verify_after_merge.get("verify_retries", 0)) or 0)
        except (TypeError, ValueError):
            continue
        history = row.get("verify_history") or []
        checked = oracle.get("checked_paths") or []
        if retries < 1 or retries > 2 or not isinstance(history, list) or len(history) < 2:
            continue
        if not isinstance(checked, list) or not checked:
            continue
        if row.get("reverify_endpoint") != "/api/sessions/{session_id}/execute/reverify":
            continue
        repair_history = row.get("repair_history") or []
        if not isinstance(repair_history, list) or not repair_history:
            continue
        last_repair = repair_history[-1]
        if not isinstance(last_repair, dict):
            continue
        if last_repair.get("agent") not in {"cursor", "codex"}:
            continue
        if last_repair.get("status") != "merged":
            continue
        oracle_after = last_repair.get("oracle_after")
        if not isinstance(oracle_after, dict) or oracle_after.get("verdict") != "pass":
            continue
        return True
    return False


def _check_durable_completed_steps(run: dict[str, Any]) -> bool:
    steps = run.get("completed_steps")
    if not isinstance(steps, list) or not steps:
        return False
    row = steps[0]
    if not isinstance(row, dict):
        return False
    step_id = str(row.get("step") or "")
    if not step_id.startswith("turn_") or "_round_" not in step_id:
        return False
    if not str(row.get("content") or "").strip():
        return False
    if row.get("agent") not in {"cursor", "codex", "claude"}:
        return False
    turns = run.get("turns") or []
    if not turns:
        return False
    last = turns[-1]
    return last.get("status") == "partial" and bool(last.get("succeeded_agents"))


def _check_adversarial_badge_payload(payload: dict[str, Any]) -> list[str]:
    from agent_lab.adversarial_gate import badge_tone

    errors: list[str] = []
    if payload.get("blocking") is not False:
        errors.append("expected blocking=false (non-blocking badge)")
    cases = payload.get("cases") or []
    if not isinstance(cases, list) or not cases:
        return errors + ["expected non-empty cases[]"]
    for idx, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"cases[{idx}] must be an object")
            continue
        note = case.get("adversarial_note")
        expected = case.get("badge_tone")
        if not isinstance(note, str) or not note.strip():
            errors.append(f"cases[{idx}] missing adversarial_note")
            continue
        if expected not in {"lgtm", "warning"}:
            errors.append(f"cases[{idx}] badge_tone must be lgtm|warning")
            continue
        if badge_tone(note) != expected:
            errors.append(f"cases[{idx}] badge_tone expected {expected!r}, got {badge_tone(note)!r}")
    return errors


def _check_specialist_artifact_only(run: dict[str, Any]) -> bool:
    last_turn = run.get("last_turn") or {}
    context = last_turn.get("context") or {}
    agents = context.get("agents") or []
    if not isinstance(agents, list):
        return False
    return any(
        row.get("agent") == "cursor"
        and row.get("parallel_round") == 2
        and row.get("context_mode") == "artifact_only"
        and row.get("recent_max_chars") == 1200
        and row.get("peer_suppressed") is True
        and (row.get("layer_chars") or {}).get("recent", 99999) <= 1300
        for row in agents
        if isinstance(row, dict)
    )


def _check_bridge_degraded_run(run: dict[str, Any]) -> bool:
    return any(
        t.get("mode") == "discuss" and t.get("status") == "completed"
        for t in run.get("turns") or []
        if isinstance(t, dict)
    )


def _cursor_row(payload: dict[str, Any]) -> dict[str, Any] | None:
    agents = payload.get("agents") or []
    if not isinstance(agents, list):
        return None
    for row in agents:
        if isinstance(row, dict) and row.get("id") == "cursor":
            return row
    return None


def _check_bridge_degraded_payload(payload: dict[str, Any]) -> list[str]:
    row = _cursor_row(payload)
    if row is None:
        return ["cursor health row missing"]
    errors: list[str] = []
    if row.get("ready") is not False:
        errors.append("cursor.ready expected false")
    if row.get("degraded") is not True:
        errors.append("cursor.degraded expected true")
    if not row.get("failure_code"):
        errors.append("cursor.failure_code missing")
    fallback = str(row.get("fallback") or "")
    if "Codex/Claude" not in fallback:
        errors.append("cursor.fallback missing Codex/Claude fallback")
    remediation = row.get("remediation")
    if not isinstance(remediation, list) or not remediation:
        errors.append("cursor.remediation expected non-empty list")
    return errors


def _open_objections(run: dict[str, Any], act: str) -> list[dict[str, Any]]:
    rows = run.get("objections") or []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and row.get("act") == act and row.get("status") == "open"]


def _check_objection_blocks_execute(run: dict[str, Any]) -> bool:
    blocks = _open_objections(run, "BLOCK")
    if not any(
        row.get("plan_action_index") or str(row.get("target_ref") or "").startswith("plan_action:") for row in blocks
    ):
        return False
    executions = _execs(run)
    if not executions:
        return True
    return any(
        row.get("status") in {"blocked", "blocked_objection", "blocked_isolation"}
        or row.get("error_code") == "open_objection"
        or row.get("blocked_reason") == "open_objection"
        for row in executions
    )


def _check_challenge_revises_metric(run: dict[str, Any]) -> bool:
    challenges = _open_objections(run, "CHALLENGE")
    tasks = run.get("tasks") or []
    if not isinstance(tasks, list):
        return False
    blocked_task_ids = {
        str(row.get("id"))
        for row in tasks
        if isinstance(row, dict) and row.get("status") == "blocked" and row.get("id")
    }
    return any(str(row.get("task_id") or "") in blocked_task_ids for row in challenges)


def _check_mailbox_handoff(run: dict[str, Any]) -> bool:
    mailbox = run.get("mailbox") or []
    if not isinstance(mailbox, list) or not mailbox:
        return False
    unread = run.get("mailbox_unread") or {}
    if not isinstance(unread, dict):
        return False
    for row in mailbox:
        if not isinstance(row, dict):
            continue
        target = str(row.get("to") or "").strip()
        if not target or row.get("read") is not False:
            continue
        if int(unread.get(target) or 0) >= 1:
            return bool(str(row.get("from") or "").strip() and str(row.get("body") or "").strip())
    return False


def _has_producer_reviewer_topology(run: dict[str, Any]) -> bool:
    if run.get("turn_profile") == "specialist":
        return True
    if str(run.get("_turn_topology") or "") == "producer_reviewer":
        return True
    for key in ("last_turn",):
        turn = run.get(key) or {}
        if not isinstance(turn, dict):
            continue
        category = turn.get("category") or {}
        if isinstance(category, dict) and category.get("topology") == "producer_reviewer":
            return True
    return False


def _check_producer_reviewer_roles(run: dict[str, Any]) -> bool:
    turns = run.get("turns") or []
    if not isinstance(turns, list) or not turns:
        return False
    last = turns[-1]
    if not isinstance(last, dict):
        return False
    roles = last.get("roles") or {}
    if not isinstance(roles, dict) or len(roles) < 2:
        return False
    category = last.get("category") or {}
    if not isinstance(category, dict):
        return False
    role_plan = category.get("role_plan") or {}
    return bool(roles) and (category.get("topology") == "producer_reviewer" or role_plan)


def _check_capability_cwd_asymmetric(run: dict[str, Any]) -> bool:
    if not _has_producer_reviewer_topology(run):
        return False
    caps = run.get("agent_capabilities") or {}
    if not isinstance(caps, dict) or len(caps) < 2:
        return False
    roles: set[str] = set()
    for row in caps.values():
        if not isinstance(row, dict):
            continue
        role = str(row.get("cwd_role") or "").strip()
        if role:
            roles.add(role)
    if len(roles) < 2:
        return False
    agents = ((run.get("last_turn") or {}).get("context") or {}).get("agents") or []
    if not isinstance(agents, list):
        return False
    cwd_by_agent: dict[str, str] = {}
    rounds_by_agent: dict[str, int] = {}
    for row in agents:
        if not isinstance(row, dict):
            continue
        agent = str(row.get("agent") or "").strip().lower()
        cwd = str(row.get("capability_cwd") or "").strip()
        if not agent or not cwd:
            continue
        cwd_by_agent[agent] = cwd
        try:
            rounds_by_agent[agent] = int(row.get("parallel_round") or 0)
        except (TypeError, ValueError):
            rounds_by_agent[agent] = 0
    expected_agents = {"codex", "claude", "cursor"}
    if set(cwd_by_agent) != expected_agents or len(set(cwd_by_agent.values())) != 3:
        return False
    if not (
        rounds_by_agent.get("codex") == 1 and rounds_by_agent.get("claude") == 1 and rounds_by_agent.get("cursor") == 2
    ):
        return False
    turns = run.get("turns") or []
    if not isinstance(turns, list) or not turns:
        return True
    return any(
        isinstance(t, dict)
        and t.get("mode") == "discuss"
        and (
            t.get("turn_profile") == "specialist"
            or (isinstance(t.get("category"), dict) and t["category"].get("topology") == "producer_reviewer")
        )
        for t in turns
    )


def _check_specialist_asymmetric_cwd(run: dict[str, Any]) -> bool:
    """Legacy alias — route topology asymmetric cwd KPI."""
    return _check_capability_cwd_asymmetric(run)


def _check_emergence_hybrid_plan(run: dict[str, Any]) -> bool:
    reached = False
    conflict_acts = 0
    for turn in run.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        consensus = turn.get("consensus") or {}
        if isinstance(consensus, dict) and consensus.get("status") == "reached":
            reached = True
        meta = turn.get("communicate_meta") or {}
        acts = meta.get("act_counts") if isinstance(meta, dict) else None
        if isinstance(acts, dict):
            conflict_acts += int(acts.get("CHALLENGE") or 0) + int(acts.get("AMEND") or 0)
    if not reached or conflict_acts < 2:
        return False
    return any(
        isinstance(o, dict) and o.get("act") in ("CHALLENGE", "BLOCK") and o.get("status") == "resolved_accepted"
        for o in run.get("objections") or []
    )


def _folder_check_emergence_hybrid_plan(run: dict[str, Any], folder: Path) -> bool:
    from agent_lab.emergence_kpis import hybrid_action_rate

    rate, _counts = hybrid_action_rate(folder)
    return rate is not None and rate >= 0.5


def _check_category_escalation(run: dict[str, Any]) -> bool:
    for turn in run.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        category = turn.get("category") or {}
        if not isinstance(category, dict):
            continue
        if category.get("escalated_from") != "quick":
            continue
        if category.get("value") not in ("standard", "deep"):
            continue
        if not category.get("escalation_act"):
            continue
        consensus = turn.get("consensus") or {}
        if isinstance(consensus, dict) and consensus.get("status") == "reached":
            return True
    return False


def _check_discuss_challenge_resolved(run: dict[str, Any]) -> bool:
    """P3: discuss CHALLENGE가 상태에 남고 endorse로 자동 해소 + challenge_yield 측정."""
    resolved = any(
        isinstance(o, dict)
        and o.get("act") == "CHALLENGE"
        and o.get("mode") == "discuss"
        and o.get("status") == "resolved_accepted"
        and str(o.get("resolution") or "").startswith("challenger_")
        for o in run.get("objections") or []
    )
    if not resolved:
        return False
    from agent_lab.emergence_kpis import challenge_yield

    rate, _counts = challenge_yield(run)
    if rate is None or rate < 1.0:
        return False
    for turn in run.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        consensus = turn.get("consensus") or {}
        if not isinstance(consensus, dict) or consensus.get("status") != "reached":
            continue
        quality = consensus.get("quality")
        if isinstance(quality, dict) and "forced_review" in quality:
            return True
    return False


def _check_recombination_synthesis(run: dict[str, Any]) -> bool:
    """P4: 재조합 라운드 합성안이 앵커 — valid_syntheses ≥ 1, anchor round == 재조합 round."""
    for turn in run.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        consensus = turn.get("consensus") or {}
        if not isinstance(consensus, dict) or consensus.get("status") != "reached":
            continue
        recomb = consensus.get("recombination")
        if not isinstance(recomb, dict) or recomb.get("skipped"):
            continue
        if int(recomb.get("valid_syntheses") or 0) < 1:
            continue
        anchor = consensus.get("anchor") or {}
        if not isinstance(anchor, dict) or not anchor.get("id"):
            continue
        if anchor.get("parallel_round") != recomb.get("round"):
            continue
        if not consensus.get("anchor_lineage"):
            continue
        from agent_lab.emergence_kpis import recombination_kpis

        rate, _counts = recombination_kpis(run)
        return rate is not None and rate > 0
    return False


def _check_envelope_consensus_endorse(run: dict[str, Any]) -> bool:
    for turn in run.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        consensus = turn.get("consensus") or {}
        if not isinstance(consensus, dict):
            continue
        if consensus.get("status") != "reached":
            continue
        anchor = consensus.get("anchor") or {}
        if not isinstance(anchor, dict) or not str(anchor.get("excerpt") or "").strip():
            continue
        consented = consensus.get("agents_consented") or []
        if not isinstance(consented, list) or not consented:
            continue
        meta = turn.get("communicate_meta") or {}
        if isinstance(meta, dict) and int(meta.get("legacy_endorse_count") or 0) > 0:
            continue
        return True
    return False


def _check_mission_loop_dogfood_ok(run: dict[str, Any]) -> bool:
    ml = run.get("mission_loop")
    if not isinstance(ml, dict) or not ml.get("enabled"):
        return False
    if ml.get("phase") != "MISSION_DONE":
        return False
    if ml.get("circuit_breaker"):
        return False
    repairs = ml.get("action_repair_counts") or {}
    if isinstance(repairs, dict) and sum(int(v or 0) for v in repairs.values()) > 0:
        return False
    executions = _execs(run)
    return any(row.get("status") == "merged" for row in executions)


def _check_mission_loop_execute_queue(run: dict[str, Any]) -> bool:
    ml = run.get("mission_loop")
    if not isinstance(ml, dict) or not ml.get("enabled"):
        return False
    if ml.get("phase") != "EXECUTE_QUEUE":
        return False
    gate = ml.get("plan_gate") or {}
    if not isinstance(gate, dict) or gate.get("status") != "ok":
        return False
    pending = ml.get("pending_action_indices") or []
    if not isinstance(pending, list) or not pending:
        return False
    if ml.get("current_action_index") is None:
        return False
    verified = run.get("verified_loop") or {}
    goal = verified.get("loop_goal") or {}
    return bool(str(goal.get("text") or "").strip())


def _check_mission_loop_paused(run: dict[str, Any]) -> bool:
    ml = run.get("mission_loop")
    if not isinstance(ml, dict) or not ml.get("enabled"):
        return False
    if ml.get("phase") != "MISSION_PAUSED":
        return False
    if not str(ml.get("pause_reason") or "").strip():
        return False
    partial = ml.get("last_partial")
    return isinstance(partial, dict) and bool(partial.get("resume_phase"))


def _check_mission_loop_circuit_breaker(run: dict[str, Any]) -> bool:
    ml = run.get("mission_loop")
    if not isinstance(ml, dict) or not ml.get("enabled"):
        return False
    if not ml.get("circuit_breaker"):
        return False
    if not str(ml.get("circuit_breaker_reason") or "").strip():
        return False
    if ml.get("phase") not in {"MISSION_PAUSED", "PLAN_REJECT", "DISCUSS"}:
        return False
    recovery = ml.get("discuss_recovery") or {}
    return isinstance(recovery, dict) and recovery.get("pending") is True


def _check_mission_loop_plan_reject(run: dict[str, Any]) -> bool:
    ml = run.get("mission_loop")
    if not isinstance(ml, dict) or not ml.get("enabled"):
        return False
    if ml.get("phase") != "PLAN_REJECT":
        return False
    if ml.get("circuit_breaker"):
        return False
    gate = ml.get("plan_gate") or {}
    if not isinstance(gate, dict) or gate.get("status") != "reject":
        return False
    if int(gate.get("momus_round") or 0) < 1:
        return False
    return bool(str(gate.get("last_reject_reason") or "").strip())


def _check_mission_loop_verify_repair(run: dict[str, Any]) -> bool:
    ml = run.get("mission_loop")
    if not isinstance(ml, dict) or not ml.get("enabled"):
        return False
    if ml.get("phase") != "MISSION_DONE":
        return False
    repairs = ml.get("action_repair_counts") or {}
    if not isinstance(repairs, dict) or sum(int(v or 0) for v in repairs.values()) < 1:
        return False
    last_verify = ml.get("last_verify") or {}
    if not isinstance(last_verify, dict) or last_verify.get("status") != "pass":
        return False
    return any(row.get("status") == "merged" for row in _execs(run))


def _check_mission_loop_discuss_recovery(run: dict[str, Any]) -> bool:
    ml = run.get("mission_loop")
    if not isinstance(ml, dict) or not ml.get("enabled"):
        return False
    if ml.get("phase") != "DISCUSS":
        return False
    if ml.get("circuit_breaker"):
        return False
    recovery = ml.get("discuss_recovery") or {}
    if not isinstance(recovery, dict) or recovery.get("pending") is not True:
        return False
    if recovery.get("reason") != "repair_cap":
        return False
    repairs = ml.get("action_repair_counts") or {}
    max_r = int(ml.get("max_repair_per_action") or 2)
    return any(int(v or 0) >= max_r for v in repairs.values())


def _check_plan_workflow_approved(run: dict[str, Any]) -> bool:
    pw = run.get("plan_workflow") or {}
    if not isinstance(pw, dict) or not pw.get("enabled"):
        return False
    if pw.get("phase") != "APPROVED":
        return False
    loop = run.get("verified_loop") or {}
    return isinstance(loop, dict) and loop.get("status") == "running"


def _check_team_plan_only_approved(run: dict[str, Any]) -> bool:
    pw = run.get("plan_workflow") or {}
    if not isinstance(pw, dict) or pw.get("phase") != "APPROVED":
        return False
    if str(run.get("plan_intent") or "") != "plan_only":
        return False
    loop = run.get("verified_loop") or {}
    if isinstance(loop, dict) and loop.get("status") == "running":
        return False
    ml = run.get("mission_loop") or {}
    if isinstance(ml, dict) and ml.get("enabled"):
        return False
    return True


def _check_goal_loop_achieved(run: dict[str, Any]) -> bool:
    goal = run.get("session_goal") or {}
    loop = run.get("goal_loop") or {}
    if not isinstance(goal, dict) or not str(goal.get("text") or "").strip():
        return False
    if not isinstance(loop, dict) or loop.get("status") != "achieved":
        return False
    checks = loop.get("checks") or []
    return bool(
        isinstance(checks, list)
        and checks
        and isinstance(checks[-1], dict)
        and checks[-1].get("verdict") == "pass"
        and checks[-1].get("source") in {"mock", "live"}
    )


_EVIDENCE_GATE_IDS = frozenset({"plan_reread", "automated", "manual_merge", "adversarial", "cleanup"})


def _check_evidence_gates_merged_ok(run: dict[str, Any]) -> bool:
    ml = run.get("mission_loop")
    if not isinstance(ml, dict) or not ml.get("enabled"):
        return False
    gate = ml.get("plan_gate") or {}
    if not isinstance(gate, dict) or gate.get("status") != "ok":
        return False
    for row in _execs(run):
        if row.get("status") != "merged":
            continue
        gates = row.get("evidence_gates")
        if not isinstance(gates, list) or len(gates) != 5:
            return False
        by_gate = {
            str(g.get("gate") or ""): str(g.get("status") or "") for g in gates if isinstance(g, dict) and g.get("gate")
        }
        if set(by_gate) != _EVIDENCE_GATE_IDS:
            return False
        if by_gate.get("automated") != "pass":
            return False
        if by_gate.get("manual_merge") != "pass":
            return False
        if row.get("oracle_verdict") != "pass":
            return False
        return True
    return False


def _validate_evidence_jsonl(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError as exc:
        return [str(exc)]
    if len(lines) < 2:
        errors.append("evidence.jsonl expected at least 2 entries")
        return errors
    for i, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"evidence.jsonl line {i}: invalid JSON")
            continue
        if not isinstance(row, dict):
            errors.append(f"evidence.jsonl line {i}: expected object")
            continue
        if not (row.get("phase") or row.get("kind") or row.get("event")):
            errors.append(f"evidence.jsonl line {i}: missing phase/kind/event")
    return errors


def _check_evidence_ledger_stream(run: dict[str, Any]) -> bool:
    ml = run.get("mission_loop")
    if not isinstance(ml, dict) or not ml.get("enabled"):
        return False
    ledger = run.get("evidence_ledger")
    if isinstance(ledger, dict):
        try:
            count = int(ledger.get("entry_count") or 0)
        except (TypeError, ValueError):
            return False
        return count >= 2
    return True


def _check_external_handoff_attached(run: dict[str, Any]) -> bool:
    required = frozenset({"stopped_cleanly", "changed_files", "checks", "evidence_summary", "risks"})
    for row in _execs(run):
        handoff = row.get("external_handoff")
        if not isinstance(handoff, dict):
            continue
        if not required.issubset(handoff.keys()):
            return False
        if not isinstance(handoff.get("stopped_cleanly"), bool):
            return False
        if not isinstance(handoff.get("changed_files"), list):
            return False
        if not isinstance(handoff.get("checks"), list):
            return False
        if not isinstance(handoff.get("risks"), list):
            return False
        if not str(handoff.get("evidence_summary") or "").strip():
            return False
        return True
    return False


def _validate_wisdom_index_json(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [str(exc)]
    if not isinstance(payload, dict):
        return ["wisdom_index.json must be an object"]
    if payload.get("version") != 1:
        errors.append("wisdom_index.json version expected 1")
    try:
        doc_count = int(payload.get("document_count") or 0)
    except (TypeError, ValueError):
        errors.append("wisdom_index.json document_count invalid")
        doc_count = 0
    if doc_count < 2:
        errors.append("wisdom_index.json document_count expected >= 2")
    documents = payload.get("documents")
    if not isinstance(documents, list) or len(documents) < 2:
        errors.append("wisdom_index.json documents[] expected >= 2 rows")
    return errors


def _check_wisdom_index_built(run: dict[str, Any]) -> bool:
    ml = run.get("mission_loop")
    if not isinstance(ml, dict) or not ml.get("enabled"):
        return False
    refs = ml.get("wisdom_refs") or []
    if not isinstance(refs, list) or not refs:
        return False
    status = run.get("wisdom_index")
    if isinstance(status, dict):
        try:
            return int(status.get("document_count") or 0) >= 2
        except (TypeError, ValueError):
            return False
    return True


SCENARIOS: dict[str, dict[str, Any]] = {
    "discuss": {
        "label": "일반 discuss",
        "check": lambda run: (
            any(t.get("mode") == "discuss" for t in run.get("turns") or [])
            and not any(t.get("review_mode") for t in run.get("turns") or [])
        ),
    },
    "review-on": {
        "label": "쟁점 검토 ON",
        "check": lambda run: any(
            t.get("mode") == "discuss" and t.get("review_mode") is True for t in run.get("turns") or []
        ),
    },
    "plan": {
        "label": "지금 정리",
        "check": lambda run: any(
            t.get("synthesize_only") is True
            or t.get("plan_trigger") == "synthesize_only"
            or (
                isinstance(t.get("turn_policy"), dict)
                and t["turn_policy"].get("scribe_trigger") == "synthesize_only"
            )
            or (t.get("mode") == "plan" and t.get("synthesize") is True)
            for t in run.get("turns") or []
        ),
    },
    "objection_blocks_execute": {
        "label": "BLOCK objection gates execute",
        "check": _check_objection_blocks_execute,
        "workflow_ids": {"room", "room.parallel"},
        "required_keys": ("workflow_id", "run_schema_version", "objections", "turns"),
    },
    "challenge_revises_metric": {
        "label": "CHALLENGE blocks linked task",
        "check": _check_challenge_revises_metric,
        "workflow_ids": {"room", "room.parallel"},
        "required_keys": ("workflow_id", "run_schema_version", "objections", "tasks"),
        "requires_turns": False,
    },
    "mailbox_handoff": {
        "label": "mailbox unread handoff",
        "check": _check_mailbox_handoff,
        "workflow_ids": {"room.parallel"},
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "mailbox",
            "mailbox_unread",
        ),
    },
    "specialist_asymmetric_cwd": {
        "label": "capability cwd asymmetric (producer_reviewer)",
        "check": _check_capability_cwd_asymmetric,
        "workflow_ids": {"room", "room.parallel"},
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "agent_capabilities",
            "turns",
        ),
    },
    "producer-reviewer-roles": {
        "label": "producer-reviewer role plan snapshot",
        "check": _check_producer_reviewer_roles,
        "workflow_ids": {"room", "room.parallel"},
        "required_keys": ("workflow_id", "run_schema_version", "turns"),
    },
    "worktree_merge_ok": {
        "label": "worktree merge ok",
        "check": _check_worktree_merge_ok,
    },
    "worktree_reject": {
        "label": "worktree reject",
        "check": _check_worktree_reject,
    },
    "worktree_unavailable": {
        "label": "worktree unavailable",
        "check": _check_worktree_unavailable,
    },
    "merge_conflict": {
        "label": "merge conflict",
        "check": _check_merge_conflict,
    },
    "worktree_apply": {
        "label": "non-git apply",
        "check": _check_apply,
    },
    "snapshot_override_pending": {
        "label": "snapshot override pending",
        "check": _check_snapshot_override,
    },
    "pre_execute_blocked": {
        "label": "pre_execute blocked",
        "check": _check_pre_execute_blocked,
    },
    "specialist_r2_artifact_only": {
        "label": "specialist Cursor R2 artifact-only",
        "check": _check_specialist_artifact_only,
    },
    "bridge_degraded_health": {
        "label": "Cursor bridge degraded health shape",
        "check": _check_bridge_degraded_run,
        "expected_health": "expected_health.json",
    },
    "adversarial_gate_lgtm": {
        "label": "adversarial gate mock LGTM badge",
        "check": _check_adversarial_gate_lgtm,
        "expected_badges": "expected_badges.json",
    },
    "execute_verify_loop": {
        "label": "execute verify loop mock oracle pass after retry",
        "check": _check_execute_verify_loop,
    },
    "durable_completed_steps": {
        "label": "durable completed_steps partial resume snapshot",
        "check": _check_durable_completed_steps,
    },
    "goal_loop_achieved": {
        "label": "LC-L5 mock goal Oracle achieved",
        "check": _check_goal_loop_achieved,
    },
    "plan_workflow_approved": {
        "label": "Plan workflow Human approved → verified running",
        "check": _check_plan_workflow_approved,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "plan_workflow",
            "verified_loop",
            "session_goal",
            "goal_loop",
            "actions",
            "approvals",
            "executions",
        ),
    },
    "mission_loop_execute_queue": {
        "label": "mission loop plan gate ok → EXECUTE_QUEUE",
        "check": _check_mission_loop_execute_queue,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "verified_loop",
            "mission_loop",
            "actions",
            "approvals",
            "executions",
        ),
    },
    "mission_loop_paused": {
        "label": "mission loop paused with last_partial resume",
        "check": _check_mission_loop_paused,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "mission_loop",
            "actions",
            "approvals",
            "executions",
        ),
    },
    "mission_loop_circuit_breaker": {
        "label": "mission loop circuit breaker + discuss recovery",
        "check": _check_mission_loop_circuit_breaker,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "mission_loop",
            "actions",
            "approvals",
            "executions",
        ),
    },
    "envelope_consensus_endorse": {
        "label": "envelope ENDORSE consensus (LEGACY_ENDORSE=0 safe)",
        "check": _check_envelope_consensus_endorse,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "actions",
            "approvals",
            "executions",
        ),
    },
    "emergence_hybrid_plan": {
        "label": "emergence: CHALLENGE→AMEND consensus + hybrid plan refs ≥ 0.5",
        "check": _check_emergence_hybrid_plan,
        "folder_check": _folder_check_emergence_hybrid_plan,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "objections",
            "actions",
            "approvals",
            "executions",
        ),
    },
    "category_escalation_quick_to_deep": {
        "label": "topic router: conflict act escalates quick → standard/deep",
        "check": _check_category_escalation,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "objections",
            "actions",
            "approvals",
            "executions",
        ),
    },
    "discuss_challenge_resolved": {
        "label": "P3: discuss CHALLENGE harvested + auto-resolved on endorse (yield 1.0)",
        "check": _check_discuss_challenge_resolved,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "objections",
            "actions",
            "approvals",
            "executions",
        ),
    },
    "recombination_synthesis": {
        "label": "P4: recombination synthesis becomes anchor (validity > 0)",
        "check": _check_recombination_synthesis,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "objections",
            "actions",
            "approvals",
            "executions",
        ),
    },
    "mission_loop_dogfood_ok": {
        "label": "mission dogfood KPI golden path",
        "check": _check_mission_loop_dogfood_ok,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "mission_loop",
            "executions",
            "actions",
            "approvals",
        ),
    },
    "mission_loop_plan_reject": {
        "label": "mission loop Momus-lite PLAN_REJECT (C안 gate)",
        "check": _check_mission_loop_plan_reject,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "verified_loop",
            "mission_loop",
            "actions",
            "approvals",
            "executions",
        ),
    },
    "mission_loop_verify_repair": {
        "label": "mission loop verify FAIL → REPAIR → MISSION_DONE",
        "check": _check_mission_loop_verify_repair,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "mission_loop",
            "executions",
            "actions",
            "approvals",
        ),
    },
    "mission_loop_discuss_recovery": {
        "label": "mission loop repair cap → DISCUSS 백엣지 (C안 핵심)",
        "check": _check_mission_loop_discuss_recovery,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "verified_loop",
            "mission_loop",
            "executions",
            "actions",
            "approvals",
        ),
    },
    "evidence_gates_merged_ok": {
        "label": "MB-3 five evidence gates on merged execution",
        "check": _check_evidence_gates_merged_ok,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "mission_loop",
            "executions",
            "actions",
            "approvals",
        ),
    },
    "evidence_ledger_stream": {
        "label": "MB-4 evidence.jsonl append-only stream",
        "check": _check_evidence_ledger_stream,
        "expected_evidence": "evidence.jsonl",
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "mission_loop",
            "evidence_ledger",
            "executions",
            "actions",
            "approvals",
        ),
    },
    "external_handoff_attached": {
        "label": "MB-8 external runner handoff JSON on execution",
        "check": _check_external_handoff_attached,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "executions",
            "actions",
            "approvals",
        ),
    },
    "wisdom_index_built": {
        "label": "MB-10 wisdom index snapshot (evidence + notepad)",
        "check": _check_wisdom_index_built,
        "expected_evidence": "evidence.jsonl",
        "expected_wisdom_index": "wisdom_index.json",
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "mission_loop",
            "wisdom_index",
            "executions",
            "actions",
            "approvals",
        ),
    },
}


def _check_example_quick_discuss(run: dict[str, Any]) -> bool:
    turns = run.get("turns") or []
    return bool(turns) and turns[0].get("mode") == "discuss" and not _execs(run)


def _check_example_plan_approved(run: dict[str, Any]) -> bool:
    pw = run.get("plan_workflow") or {}
    return pw.get("phase") == "APPROVED"


def _check_example_mission_done(run: dict[str, Any]) -> bool:
    ml = run.get("mission_loop") or {}
    if not ml.get("enabled") or ml.get("phase") != "MISSION_DONE":
        return False
    return any(
        row.get("status") == "merged"
        and str((row.get("oracle") or {}).get("verdict") or "").lower() == "pass"
        for row in _execs(run)
    )


EXAMPLE_SCENARIOS: dict[str, dict[str, Any]] = {
    "01-quick-discuss": {
        "label": "N8 example: quick discuss",
        "check": _check_example_quick_discuss,
        "requires_turns": True,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "actions",
            "approvals",
            "executions",
        ),
    },
    "02-plan-approved": {
        "label": "N8 example: plan workflow approved",
        "check": _check_example_plan_approved,
        "requires_turns": True,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "plan_workflow",
            "actions",
            "approvals",
            "executions",
        ),
    },
    "03-mission-done": {
        "label": "N8 example: mission loop MISSION_DONE",
        "check": _check_example_mission_done,
        "requires_turns": True,
        "required_keys": (
            "workflow_id",
            "run_schema_version",
            "turns",
            "mission_loop",
            "executions",
        ),
    },
}


REQUIRED_RUN_KEYS = (
    "workflow_id",
    "run_schema_version",
    "topic",
    "agents",
    "status",
    "turns",
    "actions",
    "approvals",
    "executions",
)


def _load_run(folder: Path) -> dict[str, Any]:
    path = folder / "run.json"
    if not path.is_file():
        raise FileNotFoundError(f"missing run.json: {folder}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_baseline(name: str, folder: Path) -> list[str]:
    errors: list[str] = []
    spec = SCENARIOS.get(name) or EXAMPLE_SCENARIOS.get(name)
    if spec is None:
        return [f"unknown scenario folder: {name}"]

    try:
        run = _load_run(folder)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{name}: {exc}"]

    required_keys = tuple(spec.get("required_keys") or REQUIRED_RUN_KEYS)
    for key in required_keys:
        if key not in run:
            errors.append(f"{name}: run.json missing key {key!r}")

    if run.get("run_schema_version") != 1:
        errors.append(f"{name}: run_schema_version expected 1, got {run.get('run_schema_version')!r}")
    workflow_ids = set(spec.get("workflow_ids") or {"room.parallel"})
    if run.get("workflow_id") not in workflow_ids:
        errors.append(f"{name}: workflow_id expected {sorted(workflow_ids)!r}, got {run.get('workflow_id')!r}")

    turns = run.get("turns") or []
    requires_turns = bool(spec.get("requires_turns", True))
    if requires_turns and (not isinstance(turns, list) or not turns):
        errors.append(f"{name}: turns[] must be a non-empty list")
    elif not spec["check"](run):
        errors.append(f"{name}: scenario check failed ({spec['label']})")

    folder_check = spec.get("folder_check")
    if folder_check and not folder_check(run, folder):
        errors.append(f"{name}: folder check failed ({spec['label']})")

    expected_health = spec.get("expected_health")
    if expected_health:
        path = folder / str(expected_health)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{name}: {expected_health}: {exc}")
        else:
            errors.extend(f"{name}: {err}" for err in _check_bridge_degraded_payload(payload))

    expected_badges = spec.get("expected_badges")
    if expected_badges:
        path = folder / str(expected_badges)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{name}: {expected_badges}: {exc}")
        else:
            errors.extend(f"{name}: {err}" for err in _check_adversarial_badge_payload(payload))

    expected_evidence = spec.get("expected_evidence")
    if expected_evidence:
        path = folder / str(expected_evidence)
        if not path.is_file():
            errors.append(f"{name}: missing companion file {expected_evidence}")
        else:
            errors.extend(f"{name}: {expected_evidence}: {err}" for err in _validate_evidence_jsonl(path))

    expected_wisdom_index = spec.get("expected_wisdom_index")
    if expected_wisdom_index:
        path = folder / str(expected_wisdom_index)
        if not path.is_file():
            errors.append(f"{name}: missing companion file {expected_wisdom_index}")
        else:
            errors.extend(f"{name}: {expected_wisdom_index}: {err}" for err in _validate_wisdom_index_json(path))

    return errors


def validate_regression_fixtures() -> tuple[int, list[str]]:
    if not REGRESSION.is_dir():
        return 1, [f"regression dir missing: {REGRESSION}"]

    errors: list[str] = []
    checked = 0
    for name in SCENARIOS:
        folder = REGRESSION / name
        if not folder.is_dir():
            errors.append(f"missing fixture folder: {folder}")
            continue
        checked += 1
        errors.extend(validate_baseline(name, folder))

    if checked == 0:
        return 1, ["no regression scenarios found"]
    return (1 if errors else 0), errors


def validate_example_fixtures() -> tuple[int, list[str]]:
    if not EXAMPLES.is_dir():
        return 1, [f"examples dir missing: {EXAMPLES}"]

    errors: list[str] = []
    checked = 0
    for name in EXAMPLE_SCENARIOS:
        folder = EXAMPLES / name
        if not folder.is_dir():
            errors.append(f"missing example folder: {folder}")
            continue
        checked += 1
        errors.extend(validate_baseline(name, folder))

    if checked == 0:
        return 1, ["no example scenarios found"]
    return (1 if errors else 0), errors


def probe_api_health() -> tuple[int, list[str]]:
    url = f"{API}/api/health?probe_bridge=false"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return 0, [f"API health skipped (offline): {exc}"]

    if not payload.get("ok"):
        return 1, ["API health ok=false"]
    agents = payload.get("agents") or []
    if len(agents) < 3:
        return 1, [f"API health agents expected 3+, got {len(agents)}"]

    probe_url = f"{API}/api/health?probe_bridge=true&probe_preflight=true"
    try:
        with urllib.request.urlopen(probe_url, timeout=8) as resp:
            probe_payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return 0, [f"API bridge degraded check skipped (probe unavailable): {exc}"]

    cursor = _cursor_row(probe_payload)
    if not cursor or (cursor.get("bridge") != "error" and cursor.get("degraded") is not True):
        return 0, ["API bridge degraded check skipped (cursor bridge not degraded)"]
    shape_errors = _check_bridge_degraded_payload(probe_payload)
    if shape_errors:
        return 1, [f"API bridge degraded shape: {err}" for err in shape_errors]
    return 0, ["API bridge degraded shape OK"]


def main() -> int:
    check_api = "--api" in sys.argv
    code, errors = validate_regression_fixtures()
    for err in errors:
        print(f"FAIL: {err}", file=sys.stderr)

    if code == 0:
        print(f"OK: {len(SCENARIOS)} regression baseline(s) in {REGRESSION}")

    ex_code, ex_errors = validate_example_fixtures()
    for err in ex_errors:
        print(f"FAIL: {err}", file=sys.stderr)
    code = max(code, ex_code)

    if ex_code == 0:
        print(f"OK: {len(EXAMPLE_SCENARIOS)} example mission(s) in {EXAMPLES}")

    if check_api:
        api_code, api_msgs = probe_api_health()
        for msg in api_msgs:
            print(msg, file=sys.stderr if api_code else sys.stdout)
        code = max(code, api_code)

    return code


if __name__ == "__main__":
    raise SystemExit(main())
