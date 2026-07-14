import type { PlanExecutionRecord } from "../api/client";
import {
  executionHistoryBadge,
  executionHistoryTitle,
  resolveExecutionAction,
  type StoredPlanAction,
} from "../utils/planExecuteHistory";
import { executionStatusLabel } from "../hooks/usePlanExecute";
import { executionApprovalGate } from "../utils/executeApprovalGate";
import { oracleStatus } from "./PlanExecutePanelSupport";

type Props = {
  pending: PlanExecutionRecord;
  storedActions: StoredPlanAction[];
  busy?: boolean;
  disabled?: boolean;
  compact?: boolean;
  onApprove: () => void;
  onReject: () => void;
  onOpenPlan?: () => void;
  onReverify?: (executionId: string) => void;
};

/** ExecuteQueueBar — inline approval bar for pending plan executions.
 *
 *  Uses .exec-queue-bar / .exec-queue-bar--blocked / .exec-queue-bar--compact
 *  classes (overlays.css).
 *  Drop-in for old component that used .execute-queue-bar (legacy-bridge.css).
 *
 *  Shows: badge · title · status · artifact path/page-count ·
 *         gate block reason (if blocked) · approve/reject/diff/reverify buttons.
 *  Approve button is disabled when gate.blocked === true. Reverify only shows
 *  when the Oracle verdict failed — this is the sole surface for it while a
 *  pending execution exists, since it preempts the "work" lane (composerStackLane.ts).
 */
export function ExecuteQueueBar({
  pending,
  storedActions,
  busy,
  disabled,
  compact = false,
  onApprove,
  onReject,
  onOpenPlan,
  onReverify,
}: Props) {
  const action = resolveExecutionAction(pending, storedActions);
  const title = executionHistoryTitle(pending, action);
  const badge = executionHistoryBadge(pending);
  const status = executionStatusLabel(pending.status, pending);
  const gate = executionApprovalGate(pending);
  const pdfPath = gate.pdfPath;
  const pageCount = gate.pageCount;
  const oracleFailed = ["failed", "fail"].includes(oracleStatus(pending) ?? "");

  return (
    <div
      className={[
        "exec-queue-bar",
        compact ? "exec-queue-bar--compact" : undefined,
        gate.blocked ? "exec-queue-bar--blocked" : undefined,
      ]
        .filter(Boolean)
        .join(" ")}
      role="region"
      aria-label="실행 승인 대기"
    >
      <div className="exec-queue-bar__main">
        <span className="exec-queue-bar__badge">{badge}</span>
        <div className="exec-queue-bar__text">
          <strong className="exec-queue-bar__title">{title}</strong>
          <span className="exec-queue-bar__status">{status}</span>

          {pending.needs_artifact_review ? (
            <span className="exec-queue-bar__artifact">
              {pdfPath ? `PDF: ${pdfPath}` : "PDF: —"}
              {pageCount != null ? ` · ${pageCount}p` : " · 페이지 수 —"}
              {gate.artifactsOk ? " · 검증 OK" : " · 검증 대기"}
            </span>
          ) : pdfPath || pageCount != null ? (
            <span className="exec-queue-bar__artifact">
              {pdfPath ?? ""}
              {pageCount != null ? ` · ${pageCount}p` : ""}
            </span>
          ) : null}

          {gate.blocked && gate.reason ? (
            <span className="exec-queue-bar__gate" role="note">
              {gate.reason}
            </span>
          ) : null}
        </div>
      </div>

      <div className="exec-queue-bar__actions">
        <button
          type="button"
          className="btn btn--primary btn--sm"
          disabled={disabled || busy || gate.blocked}
          title={gate.reason ?? undefined}
          onClick={onApprove}
        >
          승인
        </button>
        <button
          type="button"
          className="btn btn--sm"
          disabled={disabled || busy}
          onClick={onReject}
        >
          거부
        </button>
        {onOpenPlan ? (
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            disabled={disabled}
            onClick={onOpenPlan}
          >
            diff 보기
          </button>
        ) : null}
        {oracleFailed && onReverify ? (
          <button
            type="button"
            className="btn btn--sm"
            disabled={disabled || busy}
            onClick={() => onReverify(pending.id)}
          >
            Oracle 재검증
          </button>
        ) : null}
      </div>
    </div>
  );
}
