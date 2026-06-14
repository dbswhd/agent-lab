import { useState } from "react";
import type { RoomObjection } from "../api/client";
import { PlanActionCard } from "./PlanActionCard";
import type { VerifiedLoopView } from "../utils/verifiedLoopView";
import { parsePlanMarkdown } from "../utils/planMarkdown";
import { useLocale } from "../i18n/useLocale";
import {
  PLAN_REJECT_TARGETS,
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

  return (
    <section
      className={`goal-loop-banner goal-loop-banner--${pending ? "open" : "achieved"}`}
      aria-label="Plan approval"
    >
      <div className="goal-loop-banner__head">
        <strong>Plan 승인</strong>
        {pending ? (
          <span className="goal-oracle-badge goal-oracle-badge--open">
            승인 대기
          </span>
        ) : (
          <span className="goal-oracle-badge goal-oracle-badge--achieved">
            승인됨
          </span>
        )}
      </div>
      {pending ? (
        <>
          <p className="goal-loop-banner__detail">
            에이전트가 작성·검토한 plan.md를 확인한 뒤 승인하면 execute 루프가
            시작됩니다.
          </p>
          {planActions.length > 0 ? (
            <div className="plan-approval-actions">
              <p className="field-label">지금 실행</p>
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
              <p className="field-label">Peer review 이의</p>
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
            <summary>plan.md 전문</summary>
            <pre className="plan-approval-preview__body">{planMd || "(empty)"}</pre>
          </details>
          <label className="field-label" htmlFor="plan-approval-goal">
            목표 (파생)
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
            검증 기준
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
            completion promise
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
              Plan 승인
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
