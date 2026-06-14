export type PlanRejectTarget = "CLARIFY" | "DRAFT" | "REFINE";

export const PLAN_REJECT_TARGETS: PlanRejectTarget[] = [
  "CLARIFY",
  "DRAFT",
  "REFINE",
];

export function isPlanWorkflowPhaseBanner(phase: string | undefined): boolean {
  const p = (phase ?? "").toUpperCase();
  return (
    p === "INTAKE" ||
    p === "CLARIFY" ||
    p === "DRAFT" ||
    p === "PEER_REVIEW" ||
    p === "REFINE"
  );
}
