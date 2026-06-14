import { useState } from "react";
import type { RoomObjection } from "../api/client";
import { PlanActionCard } from "./PlanActionCard";
import type { VerifiedLoopView } from "../utils/verifiedLoopView";
import { parsePlanMarkdown } from "../utils/planMarkdown";
import { useLocale } from "../i18n/useLocale";
import {
  PLAN_REJECT_TARGETS,
  planWorkflowGateReason,
  planWorkflowNoticeLabel,
  type PlanRejectTarget,
} from "../utils/planWorkflowView";

export type PlanRejectPayload = {
  note?: string;
  target_phase: PlanRejectTarget;
};

type Props = {
  view: VerifiedLoopView;
  planMd: string;
  phase: string;
  workflowNotice?: string;
  planGate?: Record<string, unknown> | null;
  objections?: RoomObjection[];
  busy: boolean;
  error: string | null;
  editGoal: string;
  editCriteria: string;
  editPromise: string;
  onEditGoalChange: (value: string) => void;
  onEditCriteriaChange: (value: string) => void;
  onEditPromiseChange: (value: string) => void;
  onFocusObjection?: (objectionId: string) => void;
  onApprove: () => void;
  onReject: (payload: PlanRejectPayload) => void;
};

export function PlanApprovalPanel({
  view,
  planMd,
  phase,
  workflowNotice,
  planGate = null,
  objections = [],
  busy,
  error,
  editGoal,
  editCriteria,
  editPromise,
  onEditGoalChange,
  onEditCriteriaChange,
  onEditPromiseChange,
  onFocusObjection,
  onApprove,
  onReject,
}: Props) {
  const { msg } = useLocale();
  const [rejectTarget, setRejectTarget] = useState<PlanRejectTarget>("CLARIFY");
  const [rejectNote, setRejectNote] = useState("");
  const pending = phase === "HUMAN_PENDING" || view.pendingApproval;
  const planBlocks = parsePlanMarkdown(planMd);
  const planActions = planBlocks.filter((b) => b.type === "action");
  const openObjections = objections.filter((o) => o.status === "open");
  const noticeLabel = planWorkflowNoticeLabel(workflowNotice, msg);
  const gateReason = planWorkflowGateReason(planGate);

  return (
    <section
      className={`goal-loop-banner goal-loop-banner--${pending ? "open" : "achieved"}`}
      aria-label={msg.planApprovalTitle}
    >
      <div className="goal-loop-banner__head">
        <strong>{msg.planApprovalTitle}</strong>
        {pending ? (
          <span className="goal-oracle-badge goal-oracle-badge--open">
            {msg.planApprovalPending}
          </span>
        ) : (
          <span className="goal-oracle-badge goal-oracle-badge--achieved">
            {msg.planApprovalApproved}
          </span>
        )}
      </div>
      {pending ? (
        <>
          <p className="goal-loop-banner__detail">{msg.planApprovalDetail}</p>
          {noticeLabel ? (
            <p className="plan-workflow-banner__warn">{noticeLabel}</p>
          ) : null}
          {gateReason ? (
            <p className="plan-workflow-banner__warn">
              {msg.planWorkflowGateWarn(gateReason)}
            </p>
          ) : null}
          {planActions.length > 0 ? (
            <div className="plan-approval-actions">
              <p className="field-label">{msg.planApprovalRunNow}</p>
              {planActions.map((block) =>
                block.type === "action" ? (
                  <PlanActionCard
                    key={`plan-action-${block.n}`}
                    n={block.n}
                    what={block.what}
                    where={block.where}
                    verify={block.verify}
                    refs={block.refs}
                    variant="now"
                  />
                ) : null,
              )}
            </div>
          ) : null}
          {openObjections.length > 0 ? (
            <div className="plan-approval-objections">
              <p className="field-label">{msg.planApprovalPeerObjections}</p>
              <ul className="plan-approval-objections__list">
                {openObjections.map((obj) => (
                  <li key={obj.id}>
                    <button
                      type="button"
                      className="plan-approval-objections__item"
                      disabled={!onFocusObjection}
                      onClick={() => onFocusObjection?.(obj.id)}
                    >
                      <span className="plan-approval-objections__act">
                        {obj.act}
                      </span>
                      <span className="plan-approval-objections__from">
                        {obj.from}
                      </span>
                      <span className="plan-approval-objections__body">
                        {obj.body}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <details className="plan-approval-preview">
            <summary>{msg.planApprovalPlanFull}</summary>
            <pre className="plan-approval-preview__body">{planMd || "(empty)"}</pre>
          </details>
          <label className="field-label" htmlFor="plan-approval-goal">
            {msg.planApprovalGoalDerived}
          </label>
          <input
            id="plan-approval-goal"
            type="text"
            className="field"
            value={editGoal}
            onChange={(e) => onEditGoalChange(e.target.value)}
            disabled={busy}
          />
          <label className="field-label" htmlFor="plan-approval-criteria">
            {msg.planApprovalCriteria}
          </label>
          <textarea
            id="plan-approval-criteria"
            className="field"
            rows={2}
            value={editCriteria}
            onChange={(e) => onEditCriteriaChange(e.target.value)}
            disabled={busy}
          />
          <label className="field-label" htmlFor="plan-approval-promise">
            {msg.planApprovalPromise}
          </label>
          <input
            id="plan-approval-promise"
            type="text"
            className="field"
            value={editPromise}
            onChange={(e) => onEditPromiseChange(e.target.value)}
            disabled={busy}
          />
          <div className="goal-loop-banner__controls">
            <button
              type="button"
              className="btn btn--sm btn--primary"
              disabled={busy || !editGoal.trim()}
              onClick={onApprove}
            >
              {msg.planApprovalApproveBtn}
            </button>
          </div>
          <div className="plan-approval-reject">
            <label className="field-label" htmlFor="plan-reject-target">
              {msg.planRejectTarget}
            </label>
            <select
              id="plan-reject-target"
              className="field"
              value={rejectTarget}
              disabled={busy}
              onChange={(e) =>
                setRejectTarget(e.target.value as PlanRejectTarget)
              }
            >
              {PLAN_REJECT_TARGETS.map((target) => (
                <option key={target} value={target}>
                  {target === "CLARIFY"
                    ? msg.planRejectClarify
                    : target === "DRAFT"
                      ? msg.planRejectDraft
                      : msg.planRejectRefine}
                </option>
              ))}
            </select>
            <label className="field-label" htmlFor="plan-reject-note">
              {msg.planRejectNote}
            </label>
            <input
              id="plan-reject-note"
              type="text"
              className="field"
              value={rejectNote}
              disabled={busy}
              onChange={(e) => setRejectNote(e.target.value)}
            />
            <button
              type="button"
              className="btn btn--sm"
              disabled={busy}
              onClick={() =>
                onReject({
                  target_phase: rejectTarget,
                  note: rejectNote.trim() || undefined,
                })
              }
            >
              {msg.planRejectSubmit}
            </button>
          </div>
        </>
      ) : null}
      {error ? <p className="goal-loop-banner__detail">{error}</p> : null}
    </section>
  );
}
