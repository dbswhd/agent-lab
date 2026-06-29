import type { RoomObjection } from "../api/client";
import {
  PlanApprovalPanel,
  type PlanApprovalMode,
  type PlanRejectPayload,
} from "./PlanApprovalPanel";
import { PlanApprovalStrip } from "./PlanApprovalStrip";

export type PlanApprovalHost = {
  readonly enabled: boolean;
  readonly workflowNotice?: string;
  readonly planGate?: Record<string, unknown> | null;
  readonly canExecute: boolean;
  readonly busy: boolean;
  readonly error: string | null;
  readonly onApprove: (mode: PlanApprovalMode) => void;
  readonly onReject: (payload: PlanRejectPayload) => void;
};

type Props = {
  readonly planMd: string;
  readonly approval: PlanApprovalHost;
  readonly objections: readonly RoomObjection[];
  readonly blockedReason?: string | null;
  readonly onFocusObjection?: (id: string) => void;
  readonly sessionId?: string;
  readonly onObjectionResolved?: () => void;
  readonly variant?: "full" | "strip";
  readonly onOpenFiles?: () => void;
  readonly planFileLabel?: string;
};

export function WorkPlanApprovalSection({
  planMd,
  approval,
  objections,
  blockedReason = null,
  onFocusObjection,
  sessionId,
  onObjectionResolved,
  variant = "full",
  onOpenFiles,
  planFileLabel = "plan.md",
}: Props) {
  if (!approval.enabled) return null;
  if (variant === "strip") {
    return (
      <div id="work-plan-approval" className="work-surface">
        <PlanApprovalStrip
          workflowNotice={approval.workflowNotice}
          planGate={approval.planGate}
          objections={[...objections]}
          canExecute={approval.canExecute}
          blockedReason={blockedReason}
          busy={approval.busy}
          error={approval.error}
          onFocusObjection={onFocusObjection}
          onApprove={approval.onApprove}
          onReject={approval.onReject}
          sessionId={sessionId}
          onObjectionResolved={onObjectionResolved}
          onOpenFiles={onOpenFiles}
          planFileLabel={planFileLabel}
        />
      </div>
    );
  }
  return (
    <div id="work-plan-approval" className="work-surface">
      <PlanApprovalPanel
        planMd={planMd}
        workflowNotice={approval.workflowNotice}
        planGate={approval.planGate}
        objections={[...objections]}
        canExecute={approval.canExecute}
        blockedReason={blockedReason}
        busy={approval.busy}
        error={approval.error}
        onFocusObjection={onFocusObjection}
        onApprove={approval.onApprove}
        onReject={approval.onReject}
        sessionId={sessionId}
        onObjectionResolved={onObjectionResolved}
      />
    </div>
  );
}
