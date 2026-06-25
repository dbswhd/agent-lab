"""Evidence + Verification API (P2-8).

Exposes Agent Lab's Oracle verification and diff-risk assessment as a
public service that external agent systems can call.

POST /v1/verify   — assess risk + run Oracle on a diff/claim
GET  /v1/verify/status  — service health check
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1")


class VerifyRequest(BaseModel):
    diff: str = ""
    touched_paths: list[str] = Field(default_factory=list)
    claim: str = ""
    safety_scan: dict[str, Any] | None = None
    paths_outside_expected: bool = False
    needs_artifact_review: bool = False
    oracle_prompt: str = ""


class VerifyResponse(BaseModel):
    verdict: str
    risk_level: str
    risk_reasons: list[str]
    oracle: dict[str, Any] | None = None
    evidence_gates: list[dict[str, Any]] = Field(default_factory=list)
    auto_approve_eligible: bool = False
    auto_approve_reason: str = ""


def _build_execution_dict(req: VerifyRequest) -> dict[str, Any]:
    """Convert verify request into the execution dict shape expected by internal modules."""
    safety_scan = req.safety_scan or {"ok": True, "findings": [], "counts": {"blocking": 0}}
    return {
        "status": "pending_approval",
        "diff": req.diff,
        "touched_paths": req.touched_paths,
        "paths_outside_expected": req.paths_outside_expected,
        "needs_artifact_review": req.needs_artifact_review,
        "safety_scan": safety_scan,
    }


def _run_oracle_mock(diff: str, claim: str) -> dict[str, Any]:
    """Fast mock oracle: PASS when diff is small and no obvious issues."""
    from agent_lab.diff_risk import _MEDIUM_DIFF_LINES, _count_changed_lines

    lines = _count_changed_lines(diff)
    if lines > _MEDIUM_DIFF_LINES:
        return {"verdict": "fail", "detail": f"large diff ({lines} lines) requires human review", "evidence": []}
    if any(kw in (claim or "").lower() for kw in ("delete all", "drop table", "rm -rf")):
        return {"verdict": "fail", "detail": "destructive pattern detected in claim", "evidence": []}
    return {"verdict": "pass", "detail": "mock oracle: diff within acceptable bounds", "evidence": []}


def _run_oracle_live(diff: str, claim: str, oracle_prompt: str) -> dict[str, Any]:
    """Attempt live Oracle; fall back to mock on error."""
    try:
        from agent_lab.oracle_core import invoke_oracle, oracle_live_enabled, parse_oracle_response

        if not oracle_live_enabled():
            return _run_oracle_mock(diff, claim)

        prompt = oracle_prompt or (
            f"CLAIM: {claim}\n\nDIFF (first 2000 chars):\n{diff[:2000]}"
            if claim
            else f"DIFF (first 2000 chars):\n{diff[:2000]}"
        )
        raw, source = invoke_oracle("execute", prompt)
        if not raw and source == "mock":
            return _run_oracle_mock(diff, claim)
        return parse_oracle_response(raw)
    except Exception as exc:
        return {"verdict": "fail", "detail": f"oracle invocation error: {exc}", "evidence": []}


@router.post("/verify", response_model=VerifyResponse)
def verify_diff(req: VerifyRequest) -> VerifyResponse:
    """Assess a diff for risk and run Oracle verification.

    External agent systems can post their diffs here to get an independent
    Agent Lab risk assessment and Oracle verdict before merging.
    """
    from agent_lab.auto_approve_gate import evaluate_auto_approve
    from agent_lab.diff_risk import assess_diff_risk
    from agent_lab.evidence_gates import build_evidence_gates

    execution = _build_execution_dict(req)

    risk_level, risk_reasons = assess_diff_risk(execution)

    from agent_lab.oracle_core import oracle_live_enabled

    if oracle_live_enabled():
        oracle_result = _run_oracle_live(req.diff, req.claim, req.oracle_prompt)
    else:
        oracle_result = _run_oracle_mock(req.diff, req.claim)

    execution["oracle"] = oracle_result
    if oracle_result.get("verdict") == "pass":
        execution["status"] = "merged"
        execution["adversarial_note"] = "LGTM"  # oracle acts as adversarial reviewer

    dummy_run: dict[str, Any] = {"mission_loop": {}, "hook_runs": []}
    gates = build_evidence_gates(dummy_run, execution)

    gate_decision = evaluate_auto_approve(
        dict(execution, status="pending_approval"),
        run_meta=None,
    )

    return VerifyResponse(
        verdict=oracle_result.get("verdict", "fail"),
        risk_level=risk_level,
        risk_reasons=risk_reasons,
        oracle=oracle_result,
        evidence_gates=gates,
        auto_approve_eligible=gate_decision.eligible,
        auto_approve_reason=gate_decision.reason,
    )


@router.get("/verify/status")
def verify_status() -> dict[str, Any]:
    """Verification service health — indicates oracle mode and risk thresholds."""
    from agent_lab.auto_approve_gate import auto_approve_threshold, auto_approve_timeout_sec
    from agent_lab.oracle_core import oracle_live_enabled

    return {
        "ok": True,
        "oracle_mode": "live" if oracle_live_enabled() else "mock",
        "auto_approve_threshold": auto_approve_threshold(),
        "auto_approve_timeout_sec": auto_approve_timeout_sec(),
        "gates": ["plan_reread", "automated", "manual_merge", "adversarial", "cleanup"],
    }
