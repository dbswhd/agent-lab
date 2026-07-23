"""Read-only dogfood readiness packet with explicit evidence provenance."""

from __future__ import annotations

from pathlib import Path
from statistics import mean
from typing import TypeAlias

from dogfood_readiness_manifest import (
    EvidenceTier,
    GateStatus,
    ReadinessManifest,
    RunArtifact,
    SessionKind,
    SessionRecord,
    resolve_artifact,
)

JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)


def _load_runs(manifest: ReadinessManifest) -> list[tuple[SessionRecord, RunArtifact]]:
    return [
        (
            row,
            RunArtifact.model_validate_json(
                resolve_artifact(row.run_path, Path.cwd()).read_text(encoding="utf-8")
            ),
        )
        for row in manifest.sessions
    ]


def _tier_status(statuses: list[GateStatus]) -> GateStatus:
    if statuses and all(status is GateStatus.PASS for status in statuses):
        return GateStatus.PASS
    if statuses and all(status is GateStatus.DEFERRED for status in statuses):
        return GateStatus.DEFERRED
    return GateStatus.OPEN


def build_readiness_packet(manifest: ReadinessManifest) -> dict[str, JsonValue]:
    """Aggregate provenance, repair, latency, and parity without changing defaults."""
    runs = _load_runs(manifest)
    executions = [execution for _session, run in runs for execution in run.executions]
    verdicts = [
        execution.oracle.verdict.lower()
        for execution in executions
        if execution.oracle and execution.oracle.verdict.lower() in {"pass", "fail"}
    ]
    false_success = sum(
        1
        for execution in executions
        if execution.oracle
        and execution.oracle.verdict.lower() == "pass"
        and not execution.oracle.evidence
        and not execution.oracle.checked_paths
    )
    repairs = sum(len(execution.repair_history) for execution in executions)
    plateaus = sum(
        1
        for execution in executions
        if execution.oracle
        and execution.oracle.verdict.lower() == "fail"
        and execution.verify_retries >= manifest.thresholds.retry_cap
    )
    repair_chains = sum(
        1
        for session, run in runs
        if session.kind is SessionKind.REPAIR
        and any(
            attempt.oracle_before
            and attempt.oracle_before.verdict.lower() == "fail"
            and attempt.oracle_after
            and attempt.oracle_after.verdict.lower() == "pass"
            for execution in run.executions
            for attempt in execution.repair_history
        )
    )
    success_sessions = sum(
        1
        for session, run in runs
        if session.kind is SessionKind.SUCCESS
        and any(execution.oracle and execution.oracle.verdict.lower() == "pass" for execution in run.executions)
    )
    latencies = [
        (event.closed_at - event.opened_at).total_seconds()
        for event in manifest.gate_events
    ]
    cohort_rate = (
        manifest.parity.cohort.successes / manifest.parity.cohort.sample_size
        if manifest.parity.cohort.sample_size
        else None
    )
    noncohort_rate = (
        manifest.parity.noncohort.successes / manifest.parity.noncohort.sample_size
        if manifest.parity.noncohort.sample_size
        else None
    )
    tier_rows: dict[str, JsonValue] = {}
    for tier in EvidenceTier:
        records = [row for row in manifest.evidence if row.tier is tier]
        session_rows = [row for row in manifest.sessions if row.tier is tier]
        statuses = [row.status for row in records]
        if session_rows and tier is EvidenceTier.MOCK:
            statuses.append(GateStatus.PASS if success_sessions and repair_chains else GateStatus.OPEN)
        sample_size = sum(row.sample_size for row in records) if records else len(session_rows)
        if tier is EvidenceTier.LIVE and sample_size == 0:
            statuses.append(GateStatus.OPEN)
        record_paths = [str(raw) for row in records for raw in row.raw_paths]
        session_paths = [str(row.run_path) for row in session_rows]
        tier_rows[tier.value] = {
            "status": _tier_status(statuses).value,
            "sample_size": sample_size,
            "raw_paths": list(dict.fromkeys([*record_paths, *session_paths])),
        }
    coverage = len(verdicts) / len(executions) if executions else 0.0
    parity_gap = (
        abs(cohort_rate - noncohort_rate)
        if cohort_rate is not None and noncohort_rate is not None
        else None
    )
    metrics_ok = (
        coverage >= manifest.thresholds.oracle_coverage_min
        and false_success <= manifest.thresholds.false_success_max
        and parity_gap is not None
        and parity_gap <= manifest.thresholds.parity_gap_max
        and success_sessions >= 1
        and repair_chains >= 1
    )
    tiers_ok = all(row["status"] == GateStatus.PASS for row in tier_rows.values())
    gates_ok = all(row.status is GateStatus.PASS for row in manifest.operational_gates)
    return {
        "schema_version": manifest.schema_version,
        "readiness": GateStatus.PASS if metrics_ok and tiers_ok and gates_ok else GateStatus.OPEN,
        "owner": manifest.owner,
        "commit_sha": manifest.commit_sha,
        "window": manifest.window.model_dump(mode="json"),
        "flags": manifest.flags,
        "cohort_ids": list(manifest.cohort_ids),
        "evidence_by_tier": tier_rows,
        "metrics": {
            "sample_size": len(manifest.sessions),
            "oracle_coverage": round(coverage, 4),
            "false_success_count": false_success,
            "repair_attempts": repairs,
            "repair_chain_sessions": repair_chains,
            "retry_plateau_sessions": plateaus,
            "gate_latency_seconds": {
                "count": len(latencies),
                "mean": round(mean(latencies), 3) if latencies else None,
                "max": round(max(latencies), 3) if latencies else None,
            },
            "cohort_noncohort_success_gap": round(parity_gap, 4) if parity_gap is not None else None,
        },
        "operational_gates": [row.model_dump(mode="json") for row in manifest.operational_gates],
        "default_change_authorized": False,
    }


def render_markdown(packet: dict[str, JsonValue]) -> str:
    """Render the concise, reviewable form of a readiness packet."""
    lines = [
        "# Dogfood readiness packet",
        "",
        f"Status: **{packet['readiness']}**",
        f"Owner: {packet['owner']}",
        f"Commit: `{packet['commit_sha']}`",
        "",
        "## Evidence tiers",
    ]
    tiers = packet["evidence_by_tier"]
    if isinstance(tiers, dict):
        for tier, row in tiers.items():
            if isinstance(row, dict):
                lines.append(f"- {tier}: {row.get('status')} (n={row.get('sample_size')})")
                lines.extend(f"  - raw: `{raw}`" for raw in row.get("raw_paths", []) if isinstance(raw, str))
    lines.extend(["", "## Flags and cohorts"])
    flags = packet["flags"]
    if isinstance(flags, dict):
        lines.extend(f"- `{name}={value}`" for name, value in flags.items())
    lines.append(f"- cohorts: {', '.join(packet['cohort_ids']) if isinstance(packet['cohort_ids'], list) else ''}")
    lines.extend(["", "## Operational gates"])
    gates = packet["operational_gates"]
    if isinstance(gates, list):
        for gate in gates:
            if isinstance(gate, dict):
                lines.append(
                    f"- {gate.get('id')} | {gate.get('status')} | owner={gate.get('owner')} | "
                    f"next={gate.get('next_gate')}"
                )
    lines.extend(["", "No default change is authorized by this packet.", ""])
    return "\n".join(lines)
