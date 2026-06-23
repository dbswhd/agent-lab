import type { RoomObjection } from "../api/client";
import {
  PlanApprovalPanel,
  type PlanApprovalMode,
  type PlanRejectPayload,
} from "./PlanApprovalPanel";

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
};

export function WorkPlanApprovalSection({
  planMd,
  approval,
  objections,
  blockedReason = null,
  onFocusObjection,
}: Props) {
  if (!approval.enabled) return null;
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
      />
    </div>
  );
}
