import type { PlanExecutionRecord } from "../api/client";
import {
  executionHistoryBadge,
  executionHistoryTitle,
  resolveExecutionAction,
  type StoredPlanAction,
} from "../utils/planExecuteHistory";
import { executionStatusLabel } from "../hooks/usePlanExecute";
import { executionApprovalGate } from "../utils/executeApprovalGate";

type Props = {
  pending: PlanExecutionRecord;
  storedActions: StoredPlanAction[];
  busy?: boolean;
  disabled?: boolean;
  compact?: boolean;
  onApprove: () => void;
  onReject: () => void;
  onOpenPlan?: () => void;
};

export function ExecuteQueueBar({
  pending,
  storedActions,
  busy,
  disabled,
  compact = false,
  onApprove,
  onReject,
  onOpenPlan,
}: Props) {
  const action = resolveExecutionAction(pending, storedActions);
  const title = executionHistoryTitle(pending, action);
  const badge = executionHistoryBadge(pending);
  const status = executionStatusLabel(pending.status, pending);
  const gate = executionApprovalGate(pending);
  const pdfPath = gate.pdfPath;
  const pageCount = gate.pageCount;

  return (
    <div
      className={[
        "execute-queue-bar",
        compact ? "execute-queue-bar--compact" : undefined,
        gate.blocked ? "execute-queue-bar--blocked" : undefined,
      ]
        .filter(Boolean)
        .join(" ")}
      role="region"
      aria-label="실행 승인 대기"
    >
      <div className="execute-queue-bar__main">
        <span className="execute-queue-bar__badge">{badge}</span>
        <div className="execute-queue-bar__text">
          <strong className="execute-queue-bar__title">{title}</strong>
          <span className="execute-queue-bar__status">{status}</span>
          {pending.needs_artifact_review ? (
            <span className="execute-queue-bar__artifact">
              {pdfPath ? `PDF: ${pdfPath}` : "PDF: —"}
              {pageCount != null ? ` · ${pageCount}p` : " · 페이지 수 —"}
              {gate.artifactsOk ? " · 검증 OK" : " · 검증 대기"}
            </span>
          ) : pdfPath || pageCount != null ? (
            <span className="execute-queue-bar__artifact">
              {pdfPath ? pdfPath : ""}
              {pageCount != null ? ` · ${pageCount}p` : ""}
            </span>
          ) : null}
          {gate.blocked && gate.reason ? (
            <span className="execute-queue-bar__gate" role="note">
              {gate.reason}
            </span>
          ) : null}
        </div>
      </div>
      <div className="execute-queue-bar__actions">
        <button
          type="button"
          className="room-plan-btn room-plan-btn--accent"
          disabled={disabled || busy || gate.blocked}
          title={gate.reason ?? undefined}
          onClick={onApprove}
        >
          승인
        </button>
        <button
          type="button"
          className="room-plan-btn"
          disabled={disabled || busy}
          onClick={onReject}
        >
          거부
        </button>
        {onOpenPlan ? (
          <button
            type="button"
            className="room-plan-btn execute-queue-bar__detail"
            disabled={disabled}
            onClick={onOpenPlan}
          >
            diff 보기
          </button>
        ) : null}
      </div>
    </div>
  );
}
