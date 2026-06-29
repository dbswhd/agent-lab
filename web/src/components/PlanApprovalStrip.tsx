import { useState } from "react";
import { resolveSessionObjection, type RoomObjection } from "../api/client";
import { useLocale } from "../i18n/useLocale";
import {
  planWorkflowGateReason,
  planWorkflowNoticeLabel,
} from "../utils/planWorkflowView";
import type { PlanApprovalMode, PlanRejectPayload } from "./PlanApprovalPanel";

type Props = {
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
  readonly sessionId?: string;
  readonly onObjectionResolved?: () => void;
  readonly onOpenFiles?: () => void;
  readonly planFileLabel?: string;
};

const EMPTY_OBJECTIONS: readonly RoomObjection[] = [];

export function PlanApprovalStrip({
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
  sessionId,
  onObjectionResolved,
  onOpenFiles,
  planFileLabel = "plan.md",
}: Props) {
  const { msg } = useLocale();
  const [revisionOpen, setRevisionOpen] = useState(false);
  const [revisionNote, setRevisionNote] = useState("");
  const [objectionBusyId, setObjectionBusyId] = useState<string | null>(null);
  const openObjections = objections.filter((row) => row.status === "open");
  const blockingObjections = openObjections.filter(
    (row) => row.act === "BLOCK",
  );
  const noticeLabel = planWorkflowNoticeLabel(workflowNotice, msg);
  const gateReason = planWorkflowGateReason(planGate);
  const approvalDisabled =
    busy || Boolean(blockedReason) || blockingObjections.length > 0;

  return (
    <section className="plan-approval-strip" aria-label={msg.planApprovalTitle}>
      <header className="plan-approval-strip__head">
        <div>
          <p className="plan-approval-strip__eyebrow">
            {msg.planApprovalPending}
          </p>
          <p className="plan-approval-strip__detail">
            {msg.planApprovalReviewDetail}
          </p>
        </div>
        {onOpenFiles ? (
          <button
            type="button"
            className="btn btn--sm btn--ghost plan-approval-strip__files"
            onClick={onOpenFiles}
          >
            {planFileLabel.split("/").pop()}
          </button>
        ) : null}
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
        <div className="plan-approval-strip__blockers" role="alert">
          <strong>{msg.planApprovalBlockingObjections}</strong>
          <ObjectionList
            objections={blockingObjections}
            onFocusObjection={onFocusObjection}
            sessionId={sessionId}
            objectionBusyId={objectionBusyId}
            onResolve={async (objection, verdict) => {
              if (!sessionId) return;
              setObjectionBusyId(objection.id);
              try {
                await resolveSessionObjection(sessionId, objection.id, verdict);
                onObjectionResolved?.();
              } finally {
                setObjectionBusyId(null);
              }
            }}
          />
        </div>
      ) : null}
      {blockedReason ? (
        <div className="plan-approval-strip__blockers" role="alert">
          <strong>{blockedReason}</strong>
        </div>
      ) : null}

      {revisionOpen ? (
        <div className="plan-approval-strip__revision">
          <label className="field-label" htmlFor="plan-revision-note-strip">
            {msg.planRejectNote}
          </label>
          <textarea
            id="plan-revision-note-strip"
            className="field"
            rows={3}
            autoFocus
            value={revisionNote}
            disabled={busy}
            placeholder={msg.planApprovalRevisionPlaceholder}
            onChange={(event) => setRevisionNote(event.target.value)}
          />
          <div className="plan-approval-strip__actions">
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
        <footer className="plan-approval-strip__footer">
          <div className="plan-approval-strip__actions">
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
            <button
              type="button"
              className="btn btn--sm btn--ghost"
              disabled={busy}
              onClick={() => setRevisionOpen(true)}
            >
              {msg.planRejectSubmit}
            </button>
          </div>
        </footer>
      )}
      {error ? <p className="goal-loop-banner__error">{error}</p> : null}
    </section>
  );
}

function ObjectionList({
  objections,
  onFocusObjection,
  sessionId,
  objectionBusyId,
  onResolve,
}: {
  readonly objections: readonly RoomObjection[];
  readonly onFocusObjection?: (objectionId: string) => void;
  readonly sessionId?: string;
  readonly objectionBusyId?: string | null;
  readonly onResolve?: (
    objection: RoomObjection,
    verdict: "accepted" | "wontfix",
  ) => void | Promise<void>;
}) {
  return (
    <ul className="plan-approval-objections__list">
      {objections.map((objection) => (
        <li key={objection.id} className="plan-approval-objections__row">
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
          {sessionId && onResolve && objection.status === "open" ? (
            <span className="plan-approval-objections__actions">
              <button
                type="button"
                className="btn btn--xs"
                disabled={objectionBusyId === objection.id}
                onClick={() => void onResolve(objection, "accepted")}
              >
                수용
              </button>
              <button
                type="button"
                className="btn btn--xs btn--ghost"
                disabled={objectionBusyId === objection.id}
                onClick={() => void onResolve(objection, "wontfix")}
              >
                기각
              </button>
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
