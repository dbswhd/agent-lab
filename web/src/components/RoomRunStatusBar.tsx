type Props = {
  longRunning: boolean;
  runLockStuck: boolean;
  onCancel: () => void;
  onReleaseLock: () => void;
  releasing?: boolean;
};

export function RoomRunStatusBar({
  longRunning,
  runLockStuck,
  onCancel,
  onReleaseLock,
  releasing = false,
}: Props) {
  if (!longRunning && !runLockStuck) return null;

  return (
    <div className="room-run-status" role="status">
      {longRunning ? (
        <span className="room-run-status__hint">장시간 실행 중…</span>
      ) : null}
      {longRunning ? (
        <button
          type="button"
          className="mac-btn-secondary mac-btn-secondary--compact"
          onClick={onCancel}
        >
          답변 중지
        </button>
      ) : null}
      {runLockStuck ? (
        <button
          type="button"
          className="mac-btn-secondary mac-btn-secondary--compact room-run-status__unlock"
          disabled={releasing}
          onClick={onReleaseLock}
        >
          {releasing ? "해제 중…" : "실행 잠금 해제"}
        </button>
      ) : null}
    </div>
  );
}
