"""Eval Surface v1 — deterministic grader unit tests (synthetic traces, no I/O)."""

from __future__ import annotations

from typing import Any

from evals.graders import (
    gate_integrity,
    generated_mock_quality,
    objection_flow,
    oracle_coverage,
    plan_contract,
    routing_contract,
    run_graders,
    session_contract,
    trace_completeness,
)


def _trace(**artifacts: Any) -> dict[str, Any]:
    return {
        "case_id": "T",
        "session_id": "sess",
        "spans": [],
        "artifacts": {
            "category": {},
            "act_counts": {},
            "objections": [],
            "actions": [],
            "approvals": [],
            "executions": [],
            "agents": [],
            "succeeded_agents": [],
            "message_count": 0,
            "agent_parallel_rounds": 0,
            "agent_reply_count": 0,
            "envelope_parse_error_count": 0,
            "session_status": "",
            **artifacts,
        },
        "outcome": {"final_oracle_verdict": None},
    }


def _result(result: dict[str, Any] | None) -> dict[str, Any]:
    assert result is not None
    return result


# --- routing_contract --------------------------------------------------------


def test_routing_contract_skips_without_expected_category() -> None:
    assert routing_contract(_trace(), {"case_id": "T", "expected": {}}) is None


def test_routing_contract_pass_on_match() -> None:
    trace = _trace(category={"value": "deep", "escalated_from": "quick"})
    case = {"case_id": "T", "expected": {"category": "deep", "escalated_from": "quick"}}
    result = _result(routing_contract(trace, case))
    assert result["pass"] is True


def test_routing_contract_fail_on_mismatch() -> None:
    trace = _trace(category={"value": "standard"})
    case = {"case_id": "T", "expected": {"category": "deep"}}
    result = _result(routing_contract(trace, case))
    assert result["pass"] is False


def test_routing_contract_checks_turn_policy_snapshot() -> None:
    trace = _trace(
        turn_policy={
            "init_plan_workflow": False,
            "routing_contract": {
                "route_category": "quick",
                "clarity_short_circuit": True,
                "skip_fsm_bootstrap": True,
            },
        },
    )
    case = {
        "case_id": "T",
        "expected": {
            "routing_contract": {
                "clarity_short_circuit": True,
                "skip_fsm_bootstrap": True,
                "init_plan_workflow": False,
            },
        },
    }
    result = _result(routing_contract(trace, case))
    assert result["pass"] is True


def test_routing_contract_turn_policy_only_without_category() -> None:
    trace = _trace(turn_policy={"routing_contract": {"discuss_light": True}})
    case = {"case_id": "T", "expected": {"routing_contract": {"discuss_light": True}}}
    result = _result(routing_contract(trace, case))
    assert result["pass"] is True


# --- session_contract ---------------------------------------------------------


def test_session_contract_skips_without_declared_expectations() -> None:
    assert session_contract(_trace(), {"case_id": "T", "expected": {}}) is None


def test_session_contract_passes_generated_mock_quality_signals() -> None:
    trace = _trace(
        category={
            "value": "standard",
            "agent_subset": ["cursor"],
            "role_plan": {"cursor": "proposer", "codex": "executor", "claude": "critic"},
        }
    )
    trace["turn_profile"] = "analyze"
    trace["spans"] = [
        {"name": "route", "data": {}},
        {"name": "role_plan", "data": {}},
        {"name": "room_round", "data": {}},
    ]
    case = {
        "case_id": "S3",
        "expected": {
            "turn_profile": "analyze",
            "required_spans": ["route", "role_plan", "room_round"],
            "agent_subset": ["cursor"],
            "role_plan": {"cursor": "proposer", "claude": "critic"},
        },
    }
    result = _result(session_contract(trace, case))
    assert result["pass"] is True


def test_session_contract_fails_on_missing_generated_mock_signal() -> None:
    trace = _trace(category={"value": "quick", "agent_subset": ["cursor"]})
    trace["turn_profile"] = "quick"
    trace["spans"] = [{"name": "route", "data": {}}]
    case = {"case_id": "S1", "expected": {"turn_profile": "quick", "required_spans": ["route", "role_plan"]}}
    result = _result(session_contract(trace, case))
    assert result["pass"] is False
    assert "missing_spans" in result["reason"]


def test_generated_mock_quality_skips_fixture_case() -> None:
    assert generated_mock_quality(_trace(), {"case_id": "M3", "expected": {}}) is None


def test_generated_mock_quality_passes_room_round_signals() -> None:
    trace = _trace(
        category={"source": "profile"},
        agents=["cursor", "codex", "claude"],
        succeeded_agents=["cursor", "codex", "claude"],
        message_count=4,
        agent_parallel_rounds=1,
        agent_reply_count=3,
        envelope_parse_error_count=0,
        session_status="completed",
    )
    trace["topic"] = "quick question"
    case = {
        "case_id": "S1",
        "mock_run": {"topic": "quick question"},
        "expected": {
            "generated_mock_quality": {
                "required_agents": ["cursor", "codex", "claude"],
                "min_message_count": 4,
                "min_agent_reply_count": 3,
                "max_envelope_parse_errors": 0,
                "category_source": "profile",
                "required_category_signals": ["profile:quick"],
                "required_topic_terms": ["quick", "question"],
            }
        },
    }
    trace["artifacts"]["category"]["signals"] = ["profile:quick"]
    result = _result(generated_mock_quality(trace, case))
    assert result["pass"] is True


def test_generated_mock_quality_fails_weak_mock_session() -> None:
    trace = _trace(
        category={"source": "heuristic"},
        agents=["cursor"],
        succeeded_agents=["cursor"],
        message_count=2,
        agent_parallel_rounds=0,
        agent_reply_count=1,
        envelope_parse_error_count=1,
        session_status="failed",
    )
    trace["topic"] = "wrong"
    case = {
        "case_id": "S1",
        "mock_run": {"topic": "expected"},
        "expected": {
            "generated_mock_quality": {
                "required_agents": ["cursor", "codex", "claude"],
                "min_message_count": 4,
                "min_agent_reply_count": 3,
                "max_envelope_parse_errors": 0,
                "category_source": "profile",
                "required_category_signals": ["profile:quick"],
                "required_topic_terms": ["expected"],
            }
        },
    }
    result = _result(generated_mock_quality(trace, case))
    assert result["pass"] is False
    assert "missing_agents" in result["reason"]
    assert "agent_parallel_rounds=0" in result["reason"]


# --- gate_integrity (always-on invariant) ------------------------------------


def test_gate_integrity_passes_when_no_block() -> None:
    trace = _trace(executions=[{"id": "e1"}])
    result = _result(gate_integrity(trace, {"case_id": "T"}))
    assert result["pass"] is True


def test_gate_integrity_passes_when_block_open_and_no_execution() -> None:
    trace = _trace(objections=[{"act": "BLOCK", "status": "open"}])
    result = _result(gate_integrity(trace, {"case_id": "T"}))
    assert result["pass"] is True


def test_gate_integrity_fails_on_unresolved_block_with_execution() -> None:
    trace = _trace(objections=[{"act": "BLOCK", "status": "open"}], executions=[{"id": "e1"}])
    result = _result(gate_integrity(trace, {"case_id": "T"}))
    assert result["pass"] is False
    assert "execute_without_human_gate" in result["reason"]


def test_gate_integrity_passes_when_block_resolved() -> None:
    trace = _trace(objections=[{"act": "BLOCK", "status": "resolved_amend"}], executions=[{"id": "e1"}])
    result = _result(gate_integrity(trace, {"case_id": "T"}))
    assert result["pass"] is True


# --- objection_flow -----------------------------------------------------------


def test_objection_flow_skips_without_required_acts() -> None:
    assert objection_flow(_trace(), {"case_id": "T", "expected": {}}) is None


def test_objection_flow_pass_when_acts_present() -> None:
    trace = _trace(act_counts={"CHALLENGE": 1, "AMEND": 1})
    case = {"case_id": "T", "expected": {"required_acts": ["CHALLENGE", "AMEND"]}}
    result = _result(objection_flow(trace, case))
    assert result["pass"] is True


def test_objection_flow_fail_on_missing_act() -> None:
    trace = _trace(act_counts={"CHALLENGE": 1})
    case = {"case_id": "T", "expected": {"required_acts": ["CHALLENGE", "AMEND"]}}
    result = _result(objection_flow(trace, case))
    assert result["pass"] is False
    assert "AMEND" in result["reason"]


def test_objection_flow_block_checked_via_objections_list() -> None:
    trace = _trace(objections=[{"act": "BLOCK", "status": "open"}])
    case = {"case_id": "T", "expected": {"required_acts": ["BLOCK"]}}
    result = _result(objection_flow(trace, case))
    assert result["pass"] is True


def test_objection_flow_fail_on_shallow_amend_chain() -> None:
    trace = _trace(act_counts={"CHALLENGE": 1, "AMEND": 1})
    case = {"case_id": "T", "expected": {"required_acts": ["CHALLENGE", "AMEND"], "min_amend_chain_depth": 2}}
    result = _result(objection_flow(trace, case))
    assert result["pass"] is False


# --- plan_contract -------------------------------------------------------------


def test_plan_contract_skips_without_actions() -> None:
    assert plan_contract(_trace(), {"case_id": "T"}) is None


def test_plan_contract_pass_when_fields_present() -> None:
    trace = _trace(actions=[{"action_id": "a1", "what": "x", "where": "y", "verify": "z"}])
    result = _result(plan_contract(trace, {"case_id": "T"}))
    assert result["pass"] is True


def test_plan_contract_fail_on_missing_field() -> None:
    trace = _trace(actions=[{"action_id": "a1", "what": "x", "where": "", "verify": "z"}])
    result = _result(plan_contract(trace, {"case_id": "T"}))
    assert result["pass"] is False
    assert "a1.where" in result["reason"]


# --- oracle_coverage (opt-in) --------------------------------------------------


def test_oracle_coverage_skips_without_declared_expectation() -> None:
    trace = _trace(executions=[{"id": "e1"}])  # no oracle verdict at all
    assert oracle_coverage(trace, {"case_id": "T", "expected": {}}) is None


def test_oracle_coverage_skips_without_executions() -> None:
    case = {"case_id": "T", "expected": {"final_oracle_verdict": "pass"}}
    assert oracle_coverage(_trace(), case) is None


def test_oracle_coverage_pass_on_matching_final_verdict() -> None:
    trace = _trace(executions=[{"id": "e1", "oracle": {"verdict": "pass"}}])
    trace["outcome"]["final_oracle_verdict"] = "pass"
    case = {"case_id": "T", "expected": {"final_oracle_verdict": "pass"}}
    result = _result(oracle_coverage(trace, case))
    assert result["pass"] is True


def test_oracle_coverage_fail_on_verdict_mismatch() -> None:
    trace = _trace(executions=[{"id": "e1", "oracle": {"verdict": "fail"}}])
    trace["outcome"]["final_oracle_verdict"] = "fail"
    case = {"case_id": "T", "expected": {"final_oracle_verdict": "pass"}}
    result = _result(oracle_coverage(trace, case))
    assert result["pass"] is False


# --- trace_completeness ---------------------------------------------------------


def test_trace_completeness_always_passes_without_declared_minimum() -> None:
    trace = _trace()  # no spans at all
    trace["spans"] = []
    result = _result(trace_completeness(trace, {"case_id": "T", "expected": {}}))
    assert result["pass"] is True
    assert result["score"] == 0.0
    assert "trace_profile=full_path" in result["evidence"][0]


def test_trace_completeness_fails_below_declared_minimum() -> None:
    trace = _trace()
    trace["spans"] = [{"name": "route", "data": {}}]
    case = {"case_id": "T", "expected": {"min_completeness": 0.5}}
    result = _result(trace_completeness(trace, case))
    assert result["pass"] is False


def test_trace_completeness_uses_discuss_only_expected_span_subset() -> None:
    trace = _trace()
    trace["spans"] = [
        {"name": "route", "data": {}},
        {"name": "role_plan", "data": {}},
        {"name": "room_round", "data": {}},
        {"name": "objection", "data": {}},
    ]
    case = {"case_id": "M4", "trace_profile": "discuss_only", "expected": {"min_completeness": 1.0}}
    result = _result(trace_completeness(trace, case))
    assert result["pass"] is True
    assert result["score"] == 1.0


def test_trace_completeness_execute_path_excludes_feedback_advisor_from_required_subset() -> None:
    trace = _trace()
    trace["spans"] = [
        {"name": "route", "data": {}},
        {"name": "role_plan", "data": {}},
        {"name": "room_round", "data": {}},
        {"name": "objection", "data": {}},
        {"name": "plan_update", "data": {}},
        {"name": "human_gate", "data": {}},
        {"name": "execute", "data": {}},
        {"name": "oracle_verify", "data": {}},
    ]
    case = {"case_id": "L2", "trace_profile": "execute_path", "expected": {"min_completeness": 1.0}}
    result = _result(trace_completeness(trace, case))
    assert result["pass"] is True
    assert result["score"] == 1.0


# --- run_graders dispatcher ------------------------------------------------------


def test_run_graders_includes_only_applicable_graders() -> None:
    trace = _trace(objections=[{"act": "BLOCK", "status": "open"}])
    case = {"case_id": "M3", "trace_profile": "plan_only", "expected": {"required_acts": ["BLOCK"]}}
    results = run_graders(trace, case)
    names = {r["grader"] for r in results}
    assert names == {"gate_integrity", "objection_flow", "trace_completeness"}
