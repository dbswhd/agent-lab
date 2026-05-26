import type { RoomMode } from "../api/client";
import {
  MAX_AGENT_ROUNDS,
  MIN_AGENT_ROUNDS,
  setAgentRounds,
} from "../utils/roomPrefs";

type Props = {
  composeMode: RoomMode;
  onComposeModeChange: (mode: RoomMode) => void;
  agentRounds: number;
  onAgentRoundsChange: (rounds: number) => void;
  running: boolean;
  synthesizing?: boolean;
  showSynthesizeNow: boolean;
  onSynthesizeNow: () => void;
  reviewMode: boolean;
  onReviewModeChange: (on: boolean) => void;
};

export function RoomRunControls({
  composeMode,
  onComposeModeChange,
  agentRounds,
  onAgentRoundsChange,
  running,
  synthesizing = false,
  showSynthesizeNow,
  onSynthesizeNow,
  reviewMode,
  onReviewModeChange,
}: Props) {
  function bump(delta: number) {
    const next = Math.max(
      MIN_AGENT_ROUNDS,
      Math.min(MAX_AGENT_ROUNDS, agentRounds + delta),
    );
    if (next === agentRounds) return;
    setAgentRounds(next);
    onAgentRoundsChange(next);
  }

  return (
    <div className="room-run-controls" role="group" aria-label="룸 실행 설정">
      <div
        className="room-rounds-stepper"
        title="같은 메시지 안에서 에이전트가 몇 번 말할지 (agent_rounds)"
      >
        <span className="room-rounds-label">라운드</span>
        <button
          type="button"
          className="room-rounds-btn"
          aria-label="라운드 줄이기"
          disabled={running || agentRounds <= MIN_AGENT_ROUNDS}
          onClick={() => bump(-1)}
        >
          −
        </button>
        <span className="room-rounds-value" aria-live="polite">
          {agentRounds}
        </span>
        <button
          type="button"
          className="room-rounds-btn"
          aria-label="라운드 늘리기"
          disabled={running || agentRounds >= MAX_AGENT_ROUNDS}
          onClick={() => bump(1)}
        >
          +
        </button>
      </div>

      <div className="room-mode-bar" role="group" aria-label="룸 모드">
        <button
          type="button"
          className={`room-mode-btn${composeMode === "discuss" ? " active" : ""}`}
          disabled={running}
          onClick={() => onComposeModeChange("discuss")}
        >
          토론
        </button>
        <button
          type="button"
          className={`room-mode-btn${composeMode === "plan" ? " active" : ""}`}
          disabled={running}
          onClick={() => onComposeModeChange("plan")}
          title="메시지 전송 후 plan.md 생성"
        >
          정리 후 전송
        </button>
        {showSynthesizeNow && (
          <button
            type="button"
            className="room-mode-btn room-mode-btn--accent"
            disabled={running || synthesizing}
            aria-busy={synthesizing}
            onClick={onSynthesizeNow}
          >
            {synthesizing ? "정리 중…" : "지금 정리"}
          </button>
        )}
      </div>

      <label
        className={`room-review-toggle${reviewMode ? " room-review-toggle--on" : ""}`}
        title="이 턴만 2라운드에서 한 에이전트가 반박 담당 (로테이션)"
      >
        <input
          type="checkbox"
          checked={reviewMode}
          disabled={running}
          onChange={(e) => onReviewModeChange(e.target.checked)}
        />
        <span>쟁점 검토</span>
      </label>
    </div>
  );
}
