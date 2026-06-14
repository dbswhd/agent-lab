import type { PlanWorkflowRecord } from "../api/client";

const PRE_APPROVAL_PHASES = new Set([
  "INTAKE",
  "CLARIFY",
  "DRAFT",
  "PEER_REVIEW",
  "REFINE",
]);

/** Suggested Plan toggle when opening a session. null = use stored preference. */
export function suggestPlanToggleForWorkflow(
  workflow: PlanWorkflowRecord | undefined,
): boolean | null {
  if (!workflow?.enabled) return null;
  const phase = (workflow.phase ?? "").toUpperCase();
  if (phase === "HUMAN_PENDING") return false;
  if (phase === "APPROVED") return null;
  if (PRE_APPROVAL_PHASES.has(phase)) return true;
  return null;
}

export function isPlanWorkflowAwaitingApproval(
  workflow: PlanWorkflowRecord | undefined,
): boolean {
  return (
    Boolean(workflow?.enabled) &&
    (workflow?.phase ?? "").toUpperCase() === "HUMAN_PENDING"
  );
}

export function planWorkflowSessionActive(
  workflow: PlanWorkflowRecord | undefined,
): boolean {
  if (!workflow?.enabled) return false;
  const phase = (workflow.phase ?? "").toUpperCase();
  return phase !== "APPROVED";
}
