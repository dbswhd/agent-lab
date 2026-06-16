export type WorkDecisionKind =
  | "plan_needed"
  | "approval_required"
  | "blocked"
  | "verifying"
  | "verified"
  | "ready";

export type WorkDecisionActionId =
  | "focus_plan"
  | "focus_plan_approval"
  | "focus_execute"
  | "focus_checks"
  | "focus_evidence"
  | "open_tasks";

export type WorkDecisionCellState = "idle" | "active" | "blocked" | "ok";

export type WorkDecisionPanelCell = {
  readonly label: "Approve" | "Blocked" | "Verified";
  readonly value: string;
  readonly detail: string;
  readonly state: WorkDecisionCellState;
};

export type WorkDecisionSummary = {
  readonly kind: WorkDecisionKind;
  readonly eyebrow: string;
  readonly title: string;
  readonly detail: string;
  readonly whatToApprove: string;
  readonly whyBlocked: string;
  readonly verificationStatus: string;
  readonly primaryTarget: WorkDecisionActionId;
  readonly primaryLabel: string;
  readonly secondaryTarget?: WorkDecisionActionId;
  readonly secondaryLabel?: string;
  readonly cells: readonly WorkDecisionPanelCell[];
};
