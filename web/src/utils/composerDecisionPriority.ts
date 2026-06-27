export type ComposerDecisionTier =
  | "recovery"
  | "plan_approval"
  | "human_gate"
  | "plan_workflow";

export type ComposerDecisionInput = {
  readonly inboxPendingCount: number;
  readonly recoveryVisible: boolean;
  readonly showPlanApproval: boolean;
  readonly showHumanGate: boolean;
  readonly showPlanWorkflowBanner: boolean;
  readonly showPlanWorkflowComposerHint: boolean;
};

/** When inbox has pending items, HumanInboxPanel owns the composer action surface. */
export function pickComposerDecisionTier(
  input: ComposerDecisionInput,
): ComposerDecisionTier | null {
  if (input.inboxPendingCount > 0) return null;
  if (input.recoveryVisible) return "recovery";
  if (input.showPlanApproval) return "plan_approval";
  if (input.showHumanGate) return "human_gate";
  if (input.showPlanWorkflowBanner || input.showPlanWorkflowComposerHint) {
    return "plan_workflow";
  }
  return null;
}
