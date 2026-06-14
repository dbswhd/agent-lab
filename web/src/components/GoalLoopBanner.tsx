import type { GoalLoopView } from "../utils/goalLoopView";

type Props = {
  goalView: GoalLoopView;
  goalText: string;
  goalBusy: boolean;
  goalError: string | null;
  onGoalTextChange: (text: string) => void;
  onSave: () => void;
  onCheck: () => void;
  onContinueDiscuss: (prefill: string) => void;
};

export function GoalLoopBanner({
  goalView,
  goalText,
  goalBusy,
  goalError,
  onGoalTextChange,
  onSave,
  onCheck,
  onContinueDiscuss,
}: Props) {
  const status = goalView.loop.status ?? "unset";
  const fail = goalView.loop.last_check?.verdict === "fail";

  return (
    <section
      className={`goal-loop-banner goal-loop-banner--${status}${fail ? " goal-loop-banner--failed" : ""}`}
      aria-label="세션 목표"
    >
      <div className="goal-loop-banner__head">
        <strong>세션 목표</strong>
        {goalView.loop.status ? (
          <span
            className={`goal-oracle-badge goal-oracle-badge--${goalView.loop.status}`}
          >
            {goalView.loop.status === "achieved"
              ? "목표 달성"
              : fail
                ? "Oracle FAIL"
                : "진행 중"}
          </span>
        ) : null}
      </div>
      <div className="goal-loop-banner__controls">
        <input
          type="text"
          className="field"
          value={goalText}
          onChange={(e) => onGoalTextChange(e.target.value)}
          placeholder="Human이 판단할 세션 목표"
          disabled={goalBusy}
        />
        <button
          type="button"
          className="btn btn--sm btn--primary"
          disabled={goalBusy || !goalText.trim()}
          onClick={onSave}
        >
          목표 설정
        </button>
        {goalView.goal.text ? (
          <button
            type="button"
            className="btn btn--sm"
            disabled={goalBusy || goalView.loop.status === "achieved"}
            onClick={onCheck}
          >
            Oracle 재검
          </button>
        ) : null}
      </div>
      {goalView.loop.last_check?.detail ? (
        <p className="goal-loop-banner__detail">
          {goalView.loop.last_check.detail}
        </p>
      ) : null}
      {fail ? (
        <button
          type="button"
          className="btn btn--sm btn--ok"
          onClick={() =>
            onContinueDiscuss(
              goalView.loop.continue_prompt ??
                `세션 목표를 달성하기 위해 한 턴 더 토론해 주세요: ${goalView.loop.last_check?.detail ?? ""}`,
            )
          }
        >
          한 턴 더 토론
        </button>
      ) : null}
      {goalError ? (
        <p className="goal-loop-banner__error">{goalError}</p>
      ) : null}
    </section>
  );
}
