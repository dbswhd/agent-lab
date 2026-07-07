import type { PlanWorkflowRecord } from "../api/client";

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
