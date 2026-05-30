import type { RoomMode } from "../api/client";

type Props = {
  composeMode: RoomMode;
  onComposeModeChange: (mode: RoomMode) => void;
  running: boolean;
  synthesizing?: boolean;
  showSynthesizeNow: boolean;
  onSynthesizeNow: () => void;
};

export function RoomRunControls({
  composeMode,
  onComposeModeChange,
  running,
  synthesizing = false,
  showSynthesizeNow,
  onSynthesizeNow,
}: Props) {
  return (
    <div className="room-run-controls room-run-controls--plan" role="group" aria-label="정리">
      <div className="room-run-controls__actions">
        <button
          type="button"
          className={`room-plan-btn${composeMode === "plan" ? " is-armed" : ""}`}
          disabled={running}
          title={composeMode === "plan" ? "전송 시 plan.md 갱신" : "전송 시 토론만"}
          onClick={() =>
            onComposeModeChange(composeMode === "plan" ? "discuss" : "plan")
          }
        >
          {composeMode === "plan" ? "정리 후 보내기" : "토론만 보내기"}
        </button>
        {showSynthesizeNow && (
          <button
            type="button"
            className="room-plan-btn room-plan-btn--accent"
            disabled={running || synthesizing}
            aria-busy={synthesizing}
            title="plan.md만 갱신"
            onClick={onSynthesizeNow}
          >
            {synthesizing ? "정리 중…" : "지금 정리"}
          </button>
        )}
      </div>
    </div>
  );
}
