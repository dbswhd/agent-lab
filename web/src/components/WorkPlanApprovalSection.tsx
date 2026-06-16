import type { RoomObjection } from "../api/client";
import type { VerifiedLoopView } from "../utils/verifiedLoopView";
import { PlanApprovalPanel, type PlanRejectPayload } from "./PlanApprovalPanel";

export type PlanApprovalHost = {
  readonly enabled: boolean;
  readonly view: VerifiedLoopView;
  readonly phase: string;
  readonly workflowNotice?: string;
  readonly planGate?: Record<string, unknown> | null;
  readonly busy: boolean;
  readonly error: string | null;
  readonly editGoal: string;
  readonly editCriteria: string;
  readonly editPromise: string;
  readonly onEditGoalChange: (value: string) => void;
  readonly onEditCriteriaChange: (value: string) => void;
  readonly onEditPromiseChange: (value: string) => void;
  readonly onApprove: () => void;
  readonly onReject: (payload: PlanRejectPayload) => void;
};

type Props = {
  readonly planMd: string;
  readonly approval: PlanApprovalHost;
  readonly objections: readonly RoomObjection[];
  readonly onFocusObjection?: (id: string) => void;
};

export function WorkPlanApprovalSection({
  planMd,
  approval,
  objections,
  onFocusObjection,
}: Props) {
  if (!approval.enabled) return null;
  return (
    <div id="work-plan-approval" className="work-surface">
      <PlanApprovalPanel
        view={approval.view}
        planMd={planMd}
        phase={approval.phase}
        workflowNotice={approval.workflowNotice}
        planGate={approval.planGate}
        objections={[...objections]}
        busy={approval.busy}
        error={approval.error}
        editGoal={approval.editGoal}
        editCriteria={approval.editCriteria}
        editPromise={approval.editPromise}
        onEditGoalChange={approval.onEditGoalChange}
        onEditCriteriaChange={approval.onEditCriteriaChange}
        onEditPromiseChange={approval.onEditPromiseChange}
        onFocusObjection={onFocusObjection}
        onApprove={approval.onApprove}
        onReject={approval.onReject}
      />
    </div>
  );
}
