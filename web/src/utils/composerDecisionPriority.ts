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
  readonly planWorkflowPhase?: string;
  readonly planWorkflowNotice?: string;
  readonly clarifierInterview?: {
    readonly questions?: readonly {
      readonly prompt?: string;
      readonly answered?: boolean;
    }[];
  } | null;
};

/** Plan workflow progress lives in composer stack — no floating notice card. */
export function pickComposerDecisionTier(
  input: ComposerDecisionInput,
): ComposerDecisionTier | null {
  if (input.inboxPendingCount > 0) return null;
  if (input.showPlanApproval) return null;
  if (input.recoveryVisible) return "recovery";
  if (input.showHumanGate) return "human_gate";
  return null;
}
