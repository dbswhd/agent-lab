import { agentLabel } from "../utils/transcript";
import type { LiveMsg } from "../run/runSessionRegistry";
import { ChatBubble } from "./ChatBubble";
import { TurnProgressStrip } from "./TurnProgressStrip";
import { RoomRunStatusBar } from "./RoomRunStatusBar";

type Props = {
  totalRounds: number;
  reviewMode: boolean;
  agents: string[];
  doneKeys: Set<string>;
  active: { agent: string; round: number } | null;
  turnMessages: LiveMsg[];
  running: boolean;
  runBusy: boolean;
  longRunning?: boolean;
  runLockStuck?: boolean;
  releasingLock?: boolean;
  onStop?: () => void;
  onReleaseLock?: () => void;
};

export function TurnRunPanel({
  totalRounds,
  reviewMode,
  agents,
  doneKeys,
  active,
  turnMessages,
  running,
  runBusy,
  longRunning = false,
  runLockStuck = false,
  releasingLock = false,
  onStop,
  onReleaseLock,
}: Props) {
  const visibleTurnMessages = turnMessages.filter(
    (m) => m.role !== "system" || m.roundDivider != null,
  );

  return (
    <div className="turn-run-panel">
      <div className="turn-run-panel__header">
        <div>
          <strong>Run</strong>
          <span>현재 턴 실행</span>
        </div>
        {running || runBusy ? (
          <div className="turn-run-panel__controls">
            <button
              type="button"
              className="mac-btn-secondary mac-btn-secondary--compact"
              onClick={onStop}
            >
              답변 중지
            </button>
            <RoomRunStatusBar
              longRunning={longRunning}
              runLockStuck={runLockStuck}
              onCancel={onStop ?? (() => {})}
              onReleaseLock={onReleaseLock ?? (() => {})}
              releasing={releasingLock}
            />
          </div>
        ) : null}
      </div>

      <div className="run-progress-slot" aria-live="polite">
        <TurnProgressStrip
          totalRounds={totalRounds}
          reviewMode={reviewMode}
          agents={agents}
          doneKeys={doneKeys}
          active={active}
        />
      </div>

      {visibleTurnMessages.length > 0 ? (
        <div
          className="turn-run-panel__stream workspace-transcript-panel"
          aria-label="현재 턴 에이전트 출력"
        >
          {visibleTurnMessages.map((m) =>
            m.roundDivider != null ? (
              <div
                key={m.id}
                className="chat-round-divider"
                role="separator"
              >
                {m.body}
              </div>
            ) : (
              <ChatBubble
                key={m.id}
                message={m}
                presentation="console"
                typing={Boolean(m.typing)}
              />
            ),
          )}
        </div>
      ) : running ? (
        <p className="workspace-empty-state" role="status">
          {active
            ? `${agentLabel(active.agent)} · R${active.round} 응답 대기 중…`
            : "에이전트 턴 실행 중…"}
        </p>
      ) : (
        <p className="workspace-empty-state">
          실행 중이 아닙니다. 새 메시지를 보내면 이 턴의 진행과 출력이 표시됩니다.
        </p>
      )}
    </div>
  );
}
