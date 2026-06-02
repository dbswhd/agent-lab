type Props = {
  running: boolean;
  synthesizing?: boolean;
  showSynthesizeNow: boolean;
  onSynthesizeNow: () => void;
};

export function RoomRunControls({
  running,
  synthesizing = false,
  showSynthesizeNow,
  onSynthesizeNow,
}: Props) {
  if (!showSynthesizeNow) return null;

  return (
    <div className="room-run-controls" role="group" aria-label="plan 정리">
      <button
        type="button"
        className="room-plan-btn room-plan-btn--accent room-run-controls__synth"
        disabled={running || synthesizing}
        aria-busy={synthesizing}
        title="plan.md만 갱신"
        onClick={onSynthesizeNow}
      >
        {synthesizing ? "정리 중…" : "지금 정리"}
      </button>
    </div>
  );
}
