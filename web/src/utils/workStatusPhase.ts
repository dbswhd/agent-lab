import type { PlanExecutionRecord } from "../api/client";

export type WorkPhase =
  | "plan_draft"
  | "review_needed"
  | "execute_pending"
  | "merge_verify"
  | "done";

/** Map mission_loop.phase (Layer 6) to Work tab stepper when mission is enabled. */
export function resolveWorkPhaseFromMission(
  missionPhase?: string | null,
  resumePhase?: string | null,
): WorkPhase | null {
  if (!missionPhase?.trim()) return null;
  const phase = missionPhase.trim().toUpperCase();
  if (phase === "MISSION_PAUSED") {
    const resume = resumePhase?.trim();
    if (resume) {
      return resolveWorkPhaseFromMission(resume, null);
    }
    return "plan_draft";
  }
  if (phase === "MISSION_DONE") return "done";
  if (phase === "MERGE_REVIEW" || phase === "PLAN_REJECT")
    return "review_needed";
  if (phase === "VERIFY") return "merge_verify";
  if (phase === "EXECUTE_QUEUE" || phase === "DRY_RUN" || phase === "REPAIR") {
    return "execute_pending";
  }
  if (
    phase === "DISCUSS" ||
    phase === "PLAN_GATE" ||
    phase === "MISSION_DEFINE"
  ) {
    return "plan_draft";
  }
  return null;
}

export function resolveWorkPhase(input: {
  hasPlan: boolean;
  hasPendingExecution: boolean;
  hasDryRunDiff: boolean;
  pendingAgreement: boolean;
  latestExecution?: PlanExecutionRecord | null;
}): WorkPhase {
  const exec = input.latestExecution;
  const oraclePass = exec?.oracle?.verdict === "pass";
  if (exec?.status === "completed" && oraclePass) return "done";
  if (
    exec &&
    (exec.status === "merged" ||
      exec.status === "review_required" ||
      exec.status === "pending_approval" ||
      exec.status === "merge_conflict" ||
      Boolean(exec.oracle))
  ) {
    return "merge_verify";
  }
  if (input.hasPendingExecution) return "execute_pending";
  if (input.hasDryRunDiff || input.pendingAgreement) return "review_needed";
  if (input.hasPlan) return "plan_draft";
  return "plan_draft";
}
