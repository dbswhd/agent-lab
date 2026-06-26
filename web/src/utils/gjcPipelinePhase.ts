import type { PlanExecutionRecord } from "../api/client";
import type { PlanWorkflowRecord } from "../api/client";
import type { RuntimeSnapshot } from "../api/client";

/** GJC full pipeline phases (AL-009 Work stepper). */
export type GjcPipelinePhase =
  | "interview"
  | "plan"
  | "approve"
  | "goal"
  | "verify"
  | "done";

const PLAN_PHASES = new Set([
  "DRAFT",
  "PEER_REVIEW",
  "REFINE",
]);

const INTERVIEW_PHASES = new Set(["INTAKE", "CLARIFY"]);

const EXECUTE_MISSION_PHASES = new Set([
  "EXECUTE_QUEUE",
  "DRY_RUN",
  "MERGE_REVIEW",
  "REPAIR",
  "PLAN_GATE",
  "DISCUSS",
]);

export function resolveGjcPipelinePhase(input: {
  planWorkflow?: PlanWorkflowRecord | null;
  runtime?: RuntimeSnapshot | null;
  latestExecution?: PlanExecutionRecord | null;
  hasPlan: boolean;
}): GjcPipelinePhase {
  const exec = input.latestExecution;
  const oraclePass = exec?.oracle?.verdict === "pass";
  if (exec?.status === "completed" && oraclePass) {
    return "done";
  }

  const mlPhase = input.runtime?.mission?.phase?.trim().toUpperCase() ?? "";
  if (mlPhase === "MISSION_DONE") {
    return "done";
  }

  const workPhase = input.runtime?.work_phase;
  if (
    workPhase === "merge_verify" ||
    mlPhase === "VERIFY" ||
    Boolean(exec?.oracle)
  ) {
    return "verify";
  }

  if (
    workPhase === "execute_pending" ||
    EXECUTE_MISSION_PHASES.has(mlPhase) ||
    input.planWorkflow?.phase?.toUpperCase() === "APPROVED"
  ) {
    return "goal";
  }

  const wfPhase = input.planWorkflow?.phase?.trim().toUpperCase() ?? "";
  if (wfPhase === "HUMAN_PENDING") {
    return "approve";
  }
  if (PLAN_PHASES.has(wfPhase) || (input.hasPlan && wfPhase !== "APPROVED")) {
    return "plan";
  }
  if (
    INTERVIEW_PHASES.has(wfPhase) ||
    mlPhase === "CLARIFY" ||
    input.runtime?.gates?.plan_clarify?.open
  ) {
    return "interview";
  }

  return input.hasPlan ? "plan" : "interview";
}

export function gjcPipelineMetaLine(
  phase: GjcPipelinePhase,
  notice?: string | null,
): string | null {
  if (notice?.trim()) {
    return notice.trim();
  }
  switch (phase) {
    case "interview":
      return "Clarify goal, scope, and verify criteria before plan draft.";
    case "plan":
      return "Draft plan.md — peer architect/critic review when supervisor preset is on.";
    case "approve":
      return "Human approval gate — plan frozen until you approve.";
    case "goal":
      return "Execute approved plan actions (worktree → merge).";
    case "verify":
      return "Oracle verify + evidence gates on merged diff.";
    case "done":
      return "Mission complete — Oracle verified.";
    default:
      return null;
  }
}
