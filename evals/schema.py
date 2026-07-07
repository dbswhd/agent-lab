from __future__ import annotations

from typing import Literal, Required, TypeAlias, TypeGuard, TypedDict, cast

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class MockRun(TypedDict, total=False):
    topic: str
    turn_profile: str
    consensus_mode: bool


TraceProfile: TypeAlias = Literal["discuss_only", "plan_only", "execute_path", "full_path"]


class EvalCase(TypedDict, total=False):
    case_id: Required[str]
    tier: str
    summary: str
    fixture_session: str | None
    mock_run: MockRun
    trace_profile: TraceProfile
    input: JsonObject
    expected: JsonObject
    forbidden: list[str]
    skip_reason: str


class Span(TypedDict):
    name: str
    data: JsonObject


class EvalTrace(TypedDict):
    case_id: str
    session_id: str
    topic: str
    room_preset: str
    turn_profile: str
    spans: list[Span]
    artifacts: JsonObject
    outcome: JsonObject


GraderResult = TypedDict(
    "GraderResult",
    {
        "grader": str,
        "case_id": str,
        "session_id": str,
        "pass": bool,
        "score": float,
        "reason": str,
        "evidence": list[str],
    },
)


CaseResult = TypedDict(
    "CaseResult",
    {
        "case_id": str,
        "session_id": str | None,
        "session_source": Literal["fixture", "generated_mock", "none"],
        "status": Literal["graded", "skipped", "error"],
        "pass": bool | None,
        "reason": str,
        "graders": list[GraderResult],
    },
)

EvalSummary = TypedDict(
    "EvalSummary",
    {
        "total": int,
        "graded": int,
        "skipped": int,
        "failed": list[str],
        "skipped_case_ids": list[str],
    },
)

SupersampleT0 = TypedDict(
    "SupersampleT0",
    {
        "routing_pass_rate": float | None,
        "human_gate_bypass_count": int,
        "oracle_verdict_coverage": float | None,
        "trace_completeness_rate": float | None,
        "trace_completeness_interpretation": str,
        "objection_flow_pass_rate": float | None,
        "s_case_quality_pass_rate": float | None,
        "s_case_quality_failed": list[str],
    },
)

SupersampleT1 = TypedDict(
    "SupersampleT1",
    {
        "quickstart_commands": list[str],
        "expected_report_shape": str,
        "fork_time_minutes": int,
    },
)

SupersampleT2 = TypedDict(
    "SupersampleT2",
    {
        "external_fork_count": None,
        "external_issue_count": None,
        "external_pr_count": None,
        "gate": bool,
    },
)

Supersample = TypedDict(
    "Supersample",
    {
        "t0": SupersampleT0,
        "t1": SupersampleT1,
        "t2": SupersampleT2,
    },
)

EvalReport = TypedDict(
    "EvalReport",
    {
        "cases": list[CaseResult],
        "summary": EvalSummary,
        "supersample": Supersample,
    },
)


def is_json_value(value: object) -> TypeGuard[JsonValue]:
    if value is None or isinstance(value, bool | int | float | str):
        return True
    if isinstance(value, list):
        return all(is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and is_json_value(item) for key, item in value.items())
    return False


def as_json_object(value: object) -> JsonObject:
    result: JsonObject = {}
    if not isinstance(value, dict):
        return result
    for key, item in value.items():
        if isinstance(key, str) and is_json_value(item):
            result[key] = item
    return result


def parse_eval_case(value: object) -> EvalCase | None:
    obj = as_json_object(value)
    case_id = obj.get("case_id")
    if not isinstance(case_id, str):
        return None

    case: EvalCase = {"case_id": case_id}
    tier = obj.get("tier")
    summary = obj.get("summary")
    skip_reason = obj.get("skip_reason")
    if isinstance(tier, str):
        case["tier"] = tier
    if isinstance(summary, str):
        case["summary"] = summary
    if isinstance(skip_reason, str):
        case["skip_reason"] = skip_reason

    fixture = obj.get("fixture_session")
    if fixture is None or isinstance(fixture, str):
        case["fixture_session"] = fixture

    case_input = obj.get("input")
    expected = obj.get("expected")
    if isinstance(case_input, dict):
        case["input"] = case_input
    if isinstance(expected, dict):
        case["expected"] = expected

    forbidden = obj.get("forbidden")
    if isinstance(forbidden, list) and all(isinstance(item, str) for item in forbidden):
        case["forbidden"] = [item for item in forbidden if isinstance(item, str)]

    mock_run = obj.get("mock_run")
    if isinstance(mock_run, dict):
        parsed_mock: MockRun = {}
        topic = mock_run.get("topic")
        turn_profile = mock_run.get("turn_profile")
        consensus_mode = mock_run.get("consensus_mode")
        if isinstance(topic, str):
            parsed_mock["topic"] = topic
        if isinstance(turn_profile, str):
            parsed_mock["turn_profile"] = turn_profile
        if isinstance(consensus_mode, bool):
            parsed_mock["consensus_mode"] = consensus_mode
        case["mock_run"] = parsed_mock

    trace_profile = obj.get("trace_profile")
    if trace_profile in {"discuss_only", "plan_only", "execute_path", "full_path"}:
        case["trace_profile"] = cast(TraceProfile, trace_profile)

    return case
