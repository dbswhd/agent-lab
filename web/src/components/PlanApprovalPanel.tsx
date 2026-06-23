import { useState } from "react";
import type { RoomObjection } from "../api/client";
import { useLocale } from "../i18n/useLocale";
import { parsePlanMarkdown, renderPlanMarkdown } from "../utils/planMarkdown";
import {
  planWorkflowGateReason,
  planWorkflowNoticeLabel,
} from "../utils/planWorkflowView";

export type PlanApprovalMode = "execute" | "approve_only";

export type PlanRejectPayload = {
  readonly note?: string;
  readonly target_phase: "REFINE";
};

type Props = {
  readonly planMd: string;
  readonly workflowNotice?: string;
  readonly planGate?: Record<string, unknown> | null;
  readonly objections?: readonly RoomObjection[];
  readonly canExecute: boolean;
  readonly blockedReason?: string | null;
  readonly busy: boolean;
  readonly error: string | null;
  readonly onFocusObjection?: (objectionId: string) => void;
  readonly onApprove: (mode: PlanApprovalMode) => void;
  readonly onReject: (payload: PlanRejectPayload) => void;
};

const EMPTY_OBJECTIONS: readonly RoomObjection[] = [];

export function PlanApprovalPanel({
  planMd,
  workflowNotice,
  planGate = null,
  objections = EMPTY_OBJECTIONS,
  canExecute,
  blockedReason = null,
  busy,
  error,
  onFocusObjection,
  onApprove,
  onReject,
}: Props) {
  const { msg } = useLocale();
  const [revisionOpen, setRevisionOpen] = useState(false);
  const [revisionNote, setRevisionNote] = useState("");
  const planActions = parsePlanMarkdown(planMd).filter(
    (block) => block.type === "action",
  );
  const openObjections = objections.filter((row) => row.status === "open");
  const blockingObjections = openObjections.filter(
    (row) => row.act === "BLOCK",
  );
  const advisoryObjections = openObjections.filter(
    (row) => row.act !== "BLOCK",
  );
  const noticeLabel = planWorkflowNoticeLabel(workflowNotice, msg);
  const gateReason = planWorkflowGateReason(planGate);
  const approvalDisabled =
    busy || Boolean(blockedReason) || blockingObjections.length > 0;

  return (
    <section
      className="plan-approval-review"
      aria-label={msg.planApprovalTitle}
    >
      <header className="plan-approval-review__header">
        <div>
          <p className="plan-approval-review__eyebrow">
            {msg.planApprovalPending}
          </p>
          <h2>{msg.planApprovalReviewTitle}</h2>
          <p className="plan-approval-review__detail">
            {msg.planApprovalReviewDetail}
          </p>
        </div>
        <span className="plan-approval-review__count">
          {msg.planApprovalStepCount(planActions.length)}
        </span>
      </header>

      {noticeLabel ? (
        <p className="plan-workflow-banner__warn">{noticeLabel}</p>
      ) : null}
      {gateReason ? (
        <p className="plan-workflow-banner__warn">
          {msg.planWorkflowGateWarn(gateReason)}
        </p>
      ) : null}

      {blockingObjections.length > 0 ? (
        <div className="plan-approval-review__blockers" role="alert">
          <strong>{msg.planApprovalBlockingObjections}</strong>
          <ObjectionList
            objections={blockingObjections}
            onFocusObjection={onFocusObjection}
          />
        </div>
      ) : null}
      {blockedReason ? (
        <div className="plan-approval-review__blockers" role="alert">
          <strong>{blockedReason}</strong>
        </div>
      ) : null}

      <div className="plan-approval-review__document">
        {renderPlanMarkdown(planMd)}
      </div>

      {advisoryObjections.length > 0 ? (
        <details className="plan-approval-review__advisories">
          <summary>{msg.planApprovalPeerObjections}</summary>
          <ObjectionList
            objections={advisoryObjections}
            onFocusObjection={onFocusObjection}
          />
        </details>
      ) : null}

      {revisionOpen ? (
        <div className="plan-approval-review__revision">
          <label className="field-label" htmlFor="plan-revision-note">
            {msg.planRejectNote}
          </label>
          <textarea
            id="plan-revision-note"
            className="field"
            rows={3}
            autoFocus
            value={revisionNote}
            disabled={busy}
            placeholder={msg.planApprovalRevisionPlaceholder}
            onChange={(event) => setRevisionNote(event.target.value)}
          />
          <div className="plan-approval-review__actions">
            <button
              type="button"
              className="btn btn--sm btn--primary"
              disabled={busy || !revisionNote.trim()}
              onClick={() =>
                onReject({
                  target_phase: "REFINE",
                  note: revisionNote.trim(),
                })
              }
            >
              {msg.planRejectSubmit}
            </button>
            <button
              type="button"
              className="btn btn--sm btn--ghost"
              disabled={busy}
              onClick={() => setRevisionOpen(false)}
            >
              {msg.planApprovalCancel}
            </button>
          </div>
        </div>
      ) : (
        <footer className="plan-approval-review__footer">
          <div className="plan-approval-review__actions">
            {canExecute ? (
              <button
                type="button"
                className="btn btn--sm btn--primary"
                disabled={approvalDisabled}
                onClick={() => onApprove("execute")}
              >
                {msg.planApprovalApproveAndExecute}
              </button>
            ) : (
              <button
                type="button"
                className="btn btn--sm btn--primary"
                disabled={approvalDisabled}
                onClick={() => onApprove("approve_only")}
              >
                {msg.planApprovalApproveOnly}
              </button>
            )}
            {canExecute ? (
              <button
                type="button"
                className="btn btn--sm"
                disabled={approvalDisabled}
                onClick={() => onApprove("approve_only")}
              >
                {msg.planApprovalApproveOnly}
              </button>
            ) : null}
            <button
              type="button"
              className="btn btn--sm btn--ghost"
              disabled={busy}
              onClick={() => setRevisionOpen(true)}
            >
              {msg.planRejectSubmit}
            </button>
          </div>
          {!canExecute ? (
            <p className="plan-approval-review__hint">
              {msg.planApprovalNoExecuteHint}
            </p>
          ) : null}
        </footer>
      )}
      {error ? <p className="goal-loop-banner__error">{error}</p> : null}
    </section>
  );
}

function ObjectionList({
  objections,
  onFocusObjection,
}: {
  readonly objections: readonly RoomObjection[];
  readonly onFocusObjection?: (objectionId: string) => void;
}) {
  return (
    <ul className="plan-approval-objections__list">
      {objections.map((objection) => (
        <li key={objection.id}>
          <button
            type="button"
            className="plan-approval-objections__item"
            disabled={!onFocusObjection}
            onClick={() => onFocusObjection?.(objection.id)}
          >
            <span className="plan-approval-objections__from">
              {objection.from}
            </span>
            <span className="plan-approval-objections__body">
              {objection.body}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
