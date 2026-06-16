import type { WorkDecisionActionId } from "./workDecisionTypes";

export type WorkFocusTarget =
  | "execute"
  | "plan"
  | "plan_approval"
  | "checks"
  | "evidence";

export function workFocusElementId(target: WorkFocusTarget): string {
  switch (target) {
    case "execute":
      return "work-execute-queue";
    case "plan_approval":
      return "work-plan-approval";
    case "checks":
      return "work-merge-checks";
    case "evidence":
      return "work-evidence-gates";
    case "plan":
      return "work-plan-review";
  }
}

export function workDecisionActionElementId(
  actionId: Exclude<WorkDecisionActionId, "open_tasks">,
): string {
  switch (actionId) {
    case "focus_execute":
      return "work-execute-queue";
    case "focus_plan_approval":
      return "work-plan-approval";
    case "focus_checks":
      return "work-merge-checks";
    case "focus_evidence":
      return "work-evidence-gates";
    case "focus_plan":
      return "work-plan-review";
  }
}
