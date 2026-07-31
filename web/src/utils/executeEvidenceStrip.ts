/** Helpers for ExecuteQueueBar evidence density strip (Phase B2). */

import type { MergeChecksPayload, PlanExecutionRecord } from "../api/client";
import { oracleStatus } from "../components/PlanExecutePanelSupport";

export type ExecuteEvidenceStrip = {
  readonly diffLabel: string | null;
  readonly checksLabel: string | null;
  readonly oracleLabel: string | null;
  readonly oracleTone: "pass" | "fail" | "pending" | null;
};

export function buildExecuteEvidenceStrip(
  pending: PlanExecutionRecord,
  mergeChecks?: MergeChecksPayload | null,
): ExecuteEvidenceStrip {
  const diffStat = (pending.diff_stat || "").trim();
  const pathCount = pending.touched_paths?.length ?? 0;
  let diffLabel: string | null = null;
  if (diffStat) {
    diffLabel = diffStat.length > 64 ? `${diffStat.slice(0, 61)}…` : diffStat;
  } else if (pathCount > 0) {
    diffLabel = `${pathCount} file${pathCount === 1 ? "" : "s"}`;
  }

  let checksLabel: string | null = null;
  const checks = mergeChecks?.checks;
  if (Array.isArray(checks) && checks.length > 0) {
    const pass = checks.filter((row) => row.ok).length;
    checksLabel = `Checks ${pass}/${checks.length}`;
  } else if (
    Array.isArray(pending.evidence_gates) &&
    pending.evidence_gates.length > 0
  ) {
    const gates = pending.evidence_gates;
    const pass = gates.filter((row) => row.status === "pass").length;
    checksLabel = `Gates ${pass}/${gates.length}`;
  }

  const verdict = oracleStatus(pending);
  let oracleLabel: string | null = null;
  let oracleTone: ExecuteEvidenceStrip["oracleTone"] = null;
  if (verdict === "pass") {
    oracleLabel = "Oracle pass";
    oracleTone = "pass";
  } else if (verdict === "fail" || verdict === "failed") {
    oracleLabel = "Oracle fail";
    oracleTone = "fail";
  } else if (verdict) {
    oracleLabel = `Oracle ${verdict}`;
    oracleTone = "pending";
  }

  return { diffLabel, checksLabel, oracleLabel, oracleTone };
}
