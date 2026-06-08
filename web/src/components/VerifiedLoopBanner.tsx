import type { VerifiedLoopView } from "../utils/verifiedLoopView";

type Props = {
  view: VerifiedLoopView;
  busy: boolean;
  error: string | null;
  editGoal: string;
  editCriteria: string;
  editPromise: string;
  onEditGoalChange: (value: string) => void;
  onEditCriteriaChange: (value: string) => void;
  onEditPromiseChange: (value: string) => void;
  onApprove: () => void;
  onReject: () => void;
};

export function VerifiedLoopBanner({
  view,
  busy,
  error,
  editGoal,
  editCriteria,
  editPromise,
  onEditGoalChange,
  onEditCriteriaChange,
  onEditPromiseChange,
  onApprove,
  onReject,
}: Props) {
  const status = view.loop.status ?? "unset";
  const lastCheck = view.loop.last_check;

  return (
    <section
      className={`goal-loop-banner goal-loop-banner--${status}${view.isFailed ? " goal-loop-banner--failed" : ""}`}
      aria-label="Verified loop"
    >
      <div className="goal-loop-banner__head">
        <strong>Verified loop</strong>
        {view.isDone ? (
          <span className="goal-oracle-badge goal-oracle-badge--achieved">
            Oracle VERIFIED
          </span>
        ) : view.pendingApproval ? (
          <span className="goal-oracle-badge goal-oracle-badge--open">
            승인 대기
          </span>
        ) : view.isFailed ? (
          <span className="goal-oracle-badge goal-oracle-badge--failed">
            Circuit break
          </span>
        ) : status === "running" ? (
          <span className="goal-oracle-badge goal-oracle-badge--open">
            루프 진행 중
          </span>
        ) : null}
      </div>
      {view.pendingApproval ? (
        <>
          <p className="goal-loop-banner__detail">
            에이전트가 제안한 목표입니다. Human 승인 후 Oracle 검증 루프가
            시작됩니다.
          </p>
          <div className="goal-loop-banner__controls">
            <input
              type="text"
              className="field"
              value={editGoal}
              onChange={(e) => onEditGoalChange(e.target.value)}
              placeholder="Loop goal"
              disabled={busy}
            />
            <textarea
              className="field"
              value={editCriteria}
              onChange={(e) => onEditCriteriaChange(e.target.value)}
              placeholder="Completion criteria (Oracle checks this)"
              rows={3}
              disabled={busy}
            />
            <input
              type="text"
              className="field"
              value={editPromise}
              onChange={(e) => onEditPromiseChange(e.target.value)}
              placeholder="completion promise (DONE)"
              disabled={busy}
            />
            <button
              type="button"
              className="btn btn--sm btn--primary"
              disabled={busy || !editGoal.trim()}
              onClick={onApprove}
            >
              루프 시작
            </button>
            <button
              type="button"
              className="btn btn--sm"
              disabled={busy}
              onClick={onReject}
            >
              거절
            </button>
          </div>
        </>
      ) : (
        <>
          {view.proposedGoal ? (
            <p className="goal-loop-banner__detail">
              목표: {view.proposedGoal}
              {view.completionPromise
                ? ` · promise: ${view.completionPromise}`
                : ""}
            </p>
          ) : null}
          {lastCheck?.detail ? (
            <p className="goal-loop-banner__detail">{lastCheck.detail}</p>
          ) : null}
        </>
      )}
      {error ? <p className="goal-loop-banner__detail">{error}</p> : null}
    </section>
  );
}
