"""Deterministic v1 graders (docs/archive/rfcs/EVAL-SURFACE-V1-PLAN.md §4). No LLM judge.

Each grader takes ``(trace, case)`` and returns a grader-result dict, or
``None`` when the case doesn't declare an expectation the grader checks
(e.g. ``routing_contract`` on a case with no ``expected.category``) — a
skipped grader is not a failure and is simply omitted from the case's
result list.

``gate_integrity`` and ``trace_completeness`` are the two invariant checks
that always run — the BLOCK→execute gate is a hard, non-negotiable
invariant (CLAUDE.md), and trace completeness is always measurable once a
trace exists.
"""

from __future__ import annotations

from typing import Any

from evals.trace_export import FIXED_SPAN_NAMES, execution_oracle_verdict

TRACE_PROFILE_SPANS: dict[str, tuple[str, ...]] = {
    "discuss_only": ("route", "role_plan", "room_round", "objection"),
    "plan_only": ("route", "role_plan", "room_round", "objection", "plan_update", "human_gate"),
    "execute_path": (
        "route",
        "role_plan",
        "room_round",
        "plan_update",
        "human_gate",
        "execute",
        "oracle_verify",
    ),
    "full_path": FIXED_SPAN_NAMES,
}


def _result(
    name: str,
    trace: dict[str, Any],
    case: dict[str, Any],
    *,
    passed: bool,
    score: float,
    reason: str = "",
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "grader": name,
        "case_id": case.get("case_id", ""),
        "session_id": trace.get("session_id", ""),
        "pass": passed,
        "score": round(score, 4),
        "reason": reason,
        "evidence": evidence or [],
    }


def routing_contract(trace: dict[str, Any], case: dict[str, Any]) -> dict[str, Any] | None:
    expected = case.get("expected") or {}
    contract_expected = expected.get("routing_contract")
    turn_contract_expected = expected.get("turn_contract")
    if "category" not in expected and not isinstance(contract_expected, dict) and not isinstance(turn_contract_expected, dict):
        return None

    category = trace.get("artifacts", {}).get("category") or {}
    turn_policy = trace.get("artifacts", {}).get("turn_policy") or {}
    turn_contract = trace.get("artifacts", {}).get("turn_contract") or {}
    routing: dict[str, Any] = {}
    routing_value = turn_policy.get("routing_contract")
    if isinstance(routing_value, dict):
        routing = routing_value
    failures: list[str] = []
    evidence: list[str] = []

    if "category" in expected:
        observed = category.get("value")
        evidence.append(f"observed_category={observed!r}")
        if observed != expected["category"]:
            failures.append(f"category={observed!r} expected={expected['category']!r}")
        elif "escalated_from" in expected:
            observed_from = category.get("escalated_from")
            evidence.append(f"observed_escalated_from={observed_from!r}")
            if observed_from != expected["escalated_from"]:
                failures.append(
                    f"escalated_from={observed_from!r} expected={expected['escalated_from']!r}",
                )

    if isinstance(contract_expected, dict):
        _TURN_POLICY_EFFECT_KEYS = frozenset(
            {
                "init_plan_workflow",
                "advance_plan_workflow",
                "assign_task_owners",
                "run_scribe",
                "run_agent_round",
            }
        )
        evidence.append(f"routing_contract={routing!r}")
        for key, wanted in contract_expected.items():
            if key in _TURN_POLICY_EFFECT_KEYS:
                observed = turn_policy.get(key)
            else:
                observed = routing.get(key)
            evidence.append(f"{key}={observed!r}")
            if observed != wanted:
                failures.append(f"{key}={observed!r} expected={wanted!r}")

    if isinstance(turn_contract_expected, dict):
        evidence.append(f"turn_contract={turn_contract!r}")
        for key, wanted in turn_contract_expected.items():
            observed = turn_contract.get(key)
            evidence.append(f"turn_contract.{key}={observed!r}")
            if observed != wanted:
                failures.append(f"turn_contract.{key}={observed!r} expected={wanted!r}")

    ok = not failures
    reason = "" if ok else "; ".join(failures)
    return _result(
        "routing_contract",
        trace,
        case,
        passed=ok,
        score=1.0 if ok else 0.0,
        reason=reason,
        evidence=evidence,
    )


def session_contract(trace: dict[str, Any], case: dict[str, Any]) -> dict[str, Any] | None:
    expected = case.get("expected") or {}
    keys = {"turn_profile", "workflow_id", "required_spans", "agent_subset", "role_plan"}
    if not any(key in expected for key in keys):
        return None

    category = trace.get("artifacts", {}).get("category") or {}
    present_spans = {str(s.get("name")) for s in trace.get("spans") or [] if isinstance(s, dict)}
    failures: list[str] = []
    evidence: list[str] = []

    if "turn_profile" in expected:
        observed = trace.get("turn_profile")
        wanted = expected["turn_profile"]
        evidence.append(f"turn_profile={observed!r}")
        if observed != wanted:
            failures.append(f"turn_profile={observed!r} expected={wanted!r}")

    if "workflow_id" in expected:
        observed = trace.get("room_preset")
        wanted = expected["workflow_id"]
        evidence.append(f"workflow_id={observed!r}")
        if observed != wanted:
            failures.append(f"workflow_id={observed!r} expected={wanted!r}")

    required_spans = expected.get("required_spans") or []
    if required_spans:
        missing = sorted(str(span) for span in required_spans if str(span) not in present_spans)
        evidence.append(f"present_spans={sorted(present_spans)}")
        if missing:
            failures.append(f"missing_spans={missing}")

    if "agent_subset" in expected:
        observed = category.get("agent_subset")
        wanted = expected["agent_subset"]
        evidence.append(f"agent_subset={observed!r}")
        if observed != wanted:
            failures.append(f"agent_subset={observed!r} expected={wanted!r}")

    role_plan = expected.get("role_plan") or {}
    if role_plan:
        observed = category.get("role_plan") or {}
        evidence.append(f"role_plan={observed!r}")
        missing_roles = {agent: role for agent, role in role_plan.items() if observed.get(agent) != role}
        if missing_roles:
            failures.append(f"role_plan_mismatch={missing_roles}")

    return _result(
        "session_contract",
        trace,
        case,
        passed=not failures,
        score=1.0 if not failures else 0.0,
        reason="; ".join(failures),
        evidence=evidence,
    )


def turn_contract_runtime(trace: dict[str, Any], case: dict[str, Any]) -> dict[str, Any] | None:
    expected = (case.get("expected") or {}).get("turn_contract_runtime")
    if not isinstance(expected, dict):
        return None

    artifacts = trace.get("artifacts") or {}
    turn_contract = artifacts.get("turn_contract") or {}
    runtime_controls = turn_contract.get("runtime_controls") if isinstance(turn_contract, dict) else None
    turn_agents = artifacts.get("turn_agents")
    observed_agents = [agent for agent in turn_agents if isinstance(agent, str)] if isinstance(turn_agents, list) else []
    observed_rounds = _int_or_default(artifacts.get("agent_parallel_rounds"), 0)
    observed_consensus = artifacts.get("turn_consensus_mode")
    if not isinstance(observed_consensus, bool) and isinstance(runtime_controls, dict):
        candidate_consensus = runtime_controls.get("consensus")
        if isinstance(candidate_consensus, bool):
            observed_consensus = candidate_consensus
    failures: list[str] = []
    evidence = [
        f"turn_agents={observed_agents}",
        f"agent_parallel_rounds={observed_rounds}",
        f"turn_consensus_mode={observed_consensus!r}",
    ]

    if "agent_count" in expected:
        wanted = expected["agent_count"]
        if len(observed_agents) != wanted:
            failures.append(f"agent_count={len(observed_agents)} expected={wanted}")
    if "max_rounds" in expected:
        wanted = expected["max_rounds"]
        if observed_rounds > wanted:
            failures.append(f"agent_parallel_rounds={observed_rounds} > max={wanted}")
    if "consensus" in expected:
        wanted = expected["consensus"]
        if observed_consensus != wanted:
            failures.append(f"consensus={observed_consensus!r} expected={wanted!r}")

    return _result(
        "turn_contract_runtime",
        trace,
        case,
        passed=not failures,
        score=1.0 if not failures else 0.0,
        reason="; ".join(failures),
        evidence=evidence,
    )


def generated_mock_quality(trace: dict[str, Any], case: dict[str, Any]) -> dict[str, Any] | None:
    expected = case.get("expected") or {}
    quality = expected.get("generated_mock_quality")
    if "mock_run" not in case and not isinstance(quality, dict):
        return None
    if not isinstance(quality, dict):
        quality = {}

    artifacts = trace.get("artifacts", {})
    category = artifacts.get("category") if isinstance(artifacts.get("category"), dict) else {}
    mock_run_raw = case.get("mock_run")
    mock_run: dict[str, Any] = mock_run_raw if isinstance(mock_run_raw, dict) else {}
    required_agents = _str_list(quality.get("required_agents")) or ["cursor", "codex", "claude"]
    min_messages = _int_or_default(quality.get("min_message_count"), 2)
    min_replies = _int_or_default(quality.get("min_agent_reply_count"), len(required_agents))
    max_parse_errors = _int_or_default(quality.get("max_envelope_parse_errors"), 0)
    expected_source = quality.get("category_source")
    required_topic_terms = _str_list(quality.get("required_topic_terms"))
    required_category_signals = _str_list(quality.get("required_category_signals"))

    failures: list[str] = []
    evidence: list[str] = []

    topic = str(trace.get("topic") or "")
    expected_topic = str(mock_run.get("topic") or "")
    evidence.append(f"topic={topic!r}")
    if not topic.strip():
        failures.append("topic_empty")
    if expected_topic and topic != expected_topic:
        failures.append(f"topic={topic!r} expected={expected_topic!r}")
    missing_topic_terms = [term for term in required_topic_terms if term not in topic]
    evidence.append(f"required_topic_terms={required_topic_terms}")
    if missing_topic_terms:
        failures.append(f"missing_topic_terms={missing_topic_terms}")

    status = artifacts.get("session_status")
    evidence.append(f"session_status={status!r}")
    if status != "completed":
        failures.append(f"session_status={status!r} expected='completed'")

    agents = set(_str_list(artifacts.get("agents")))
    succeeded = set(_str_list(artifacts.get("succeeded_agents")))
    missing_agents = [agent for agent in required_agents if agent not in agents]
    missing_succeeded = [agent for agent in required_agents if agent not in succeeded]
    evidence.append(f"agents={sorted(agents)}")
    evidence.append(f"succeeded_agents={sorted(succeeded)}")
    if missing_agents:
        failures.append(f"missing_agents={missing_agents}")
    if missing_succeeded:
        failures.append(f"missing_succeeded_agents={missing_succeeded}")

    message_count = _int_or_default(artifacts.get("message_count"), 0)
    reply_count = _int_or_default(artifacts.get("agent_reply_count"), 0)
    parse_errors = _int_or_default(artifacts.get("envelope_parse_error_count"), 0)
    rounds = _int_or_default(artifacts.get("agent_parallel_rounds"), 0)
    evidence.extend(
        [
            f"message_count={message_count}",
            f"agent_reply_count={reply_count}",
            f"agent_parallel_rounds={rounds}",
            f"envelope_parse_error_count={parse_errors}",
        ]
    )
    if message_count < min_messages:
        failures.append(f"message_count={message_count} < min={min_messages}")
    if reply_count < min_replies:
        failures.append(f"agent_reply_count={reply_count} < min={min_replies}")
    if parse_errors > max_parse_errors:
        failures.append(f"envelope_parse_error_count={parse_errors} > max={max_parse_errors}")
    if rounds < 1:
        failures.append("agent_parallel_rounds=0")

    if expected_source is not None:
        observed_source = category.get("source")
        evidence.append(f"category_source={observed_source!r}")
        if observed_source != expected_source:
            failures.append(f"category_source={observed_source!r} expected={expected_source!r}")
    category_signals = _str_list(category.get("signals"))
    missing_category_signals = [signal for signal in required_category_signals if signal not in category_signals]
    evidence.append(f"category_signals={category_signals}")
    if missing_category_signals:
        failures.append(f"missing_category_signals={missing_category_signals}")

    return _result(
        "generated_mock_quality",
        trace,
        case,
        passed=not failures,
        score=1.0 if not failures else 0.0,
        reason="; ".join(failures),
        evidence=evidence,
    )


def gate_integrity(trace: dict[str, Any], case: dict[str, Any]) -> dict[str, Any] | None:
    objections = trace.get("artifacts", {}).get("objections") or []
    executions = trace.get("artifacts", {}).get("executions") or []
    unresolved = [
        o for o in objections if str(o.get("act")) == "BLOCK" and not str(o.get("status") or "").startswith("resolved")
    ]
    ok = not (unresolved and executions)
    reason = "" if ok else "execute_without_human_gate: unresolved BLOCK objection(s) alongside execution(s)"
    evidence = [f"unresolved_block_count={len(unresolved)}", f"execution_count={len(executions)}"]
    return _result("gate_integrity", trace, case, passed=ok, score=1.0 if ok else 0.0, reason=reason, evidence=evidence)


def objection_flow(trace: dict[str, Any], case: dict[str, Any]) -> dict[str, Any] | None:
    expected = case.get("expected") or {}
    required = expected.get("required_acts") or []
    if not required:
        return None
    act_counts = trace.get("artifacts", {}).get("act_counts") or {}
    objections = trace.get("artifacts", {}).get("objections") or []
    objection_acts = {str(o.get("act")) for o in objections}
    missing = [a for a in required if int(act_counts.get(a, 0) or 0) < 1 and a not in objection_acts]
    ok = not missing
    reason_parts = [f"missing required acts: {missing}"] if missing else []
    if ok and "min_amend_chain_depth" in expected:
        depth = int(act_counts.get("AMEND", 0) or 0)
        min_depth = expected["min_amend_chain_depth"]
        ok = depth >= min_depth
        if not ok:
            reason_parts.append(f"amend_chain_depth={depth} < min={min_depth}")
    reason = "; ".join(reason_parts)
    evidence = [f"act_counts={act_counts}", f"objection_acts={sorted(objection_acts)}"]
    return _result("objection_flow", trace, case, passed=ok, score=1.0 if ok else 0.0, reason=reason, evidence=evidence)


def plan_contract(trace: dict[str, Any], case: dict[str, Any]) -> dict[str, Any] | None:
    actions = trace.get("artifacts", {}).get("actions") or []
    if not actions:
        return None
    missing_fields = [
        f"{a.get('action_id', '?')}.{field}"
        for a in actions
        for field in ("what", "where", "verify")
        if not str(a.get(field) or "").strip()
    ]
    ok = not missing_fields
    reason = "" if ok else f"actions missing required fields: {missing_fields}"
    return _result(
        "plan_contract", trace, case, passed=ok, score=1.0 if ok else 0.0, reason=reason, evidence=[f"action_count={len(actions)}"]
    )


def oracle_coverage(trace: dict[str, Any], case: dict[str, Any]) -> dict[str, Any] | None:
    """Opt-in: only cases that declare an oracle expectation are graded here.

    Not every execution needs an Oracle verdict (e.g. a worktree-merge-only
    case may have no verify step) — absence of a declared expectation means
    "not applicable", not "fail".
    """
    expected = case.get("expected") or {}
    if "final_oracle_verdict" not in expected and "min_oracle_coverage" not in expected:
        return None
    executions = trace.get("artifacts", {}).get("executions") or []
    if not executions:
        return None
    with_verdict = [e for e in executions if isinstance(e, dict) and execution_oracle_verdict(e)]
    coverage = len(with_verdict) / len(executions)
    ok = True
    reason_parts: list[str] = []
    if "min_oracle_coverage" in expected and coverage < expected["min_oracle_coverage"]:
        ok = False
        reason_parts.append(f"coverage={coverage:.2f} < min={expected['min_oracle_coverage']:.2f}")
    if "final_oracle_verdict" in expected:
        final_verdict = trace.get("outcome", {}).get("final_oracle_verdict")
        if final_verdict != expected["final_oracle_verdict"]:
            ok = False
            reason_parts.append(f"final_verdict={final_verdict!r} expected={expected['final_oracle_verdict']!r}")
    reason = "; ".join(reason_parts)
    evidence = [f"executions_with_verdict={len(with_verdict)}/{len(executions)}"]
    return _result("oracle_coverage", trace, case, passed=ok, score=coverage, reason=reason, evidence=evidence)


def trace_completeness(trace: dict[str, Any], case: dict[str, Any]) -> dict[str, Any] | None:
    present = {s["name"] for s in trace.get("spans") or []}
    trace_profile = str(case.get("trace_profile") or "full_path")
    expected_span_names = TRACE_PROFILE_SPANS.get(trace_profile, FIXED_SPAN_NAMES)
    expected_spans = set(expected_span_names)
    total = len(expected_span_names)
    score = (len(present & expected_spans) / total) if total else 0.0
    expected = case.get("expected") or {}
    min_completeness = expected.get("min_completeness", 0.0)
    ok = score >= min_completeness
    missing = sorted(expected_spans - present)
    reason = "" if ok else f"completeness {score:.2f} < min {min_completeness:.2f}"
    return _result(
        "trace_completeness",
        trace,
        case,
        passed=ok,
        score=score,
        reason=reason,
        evidence=[f"trace_profile={trace_profile}", f"expected_spans={sorted(expected_spans)}", f"missing_spans={missing}"],
    )


# gate_integrity and trace_completeness always run (no expected-key gate);
# the others opt in only when the case declares the relevant `expected` key.
GRADERS = (
    routing_contract,
    session_contract,
    turn_contract_runtime,
    generated_mock_quality,
    gate_integrity,
    objection_flow,
    plan_contract,
    oracle_coverage,
    trace_completeness,
)


def run_graders(trace: dict[str, Any], case: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for grader in GRADERS:
        result = grader(trace, case)
        if result is not None:
            results.append(result)
    return results


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _int_or_default(value: object, default: int) -> int:
    return value if isinstance(value, int) else default
