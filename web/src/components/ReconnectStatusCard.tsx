import { useState } from "react";
import { resumeRoomRun } from "../api/client";
import { getRoomEventHandler } from "../run/roomReconnectRegistry";

export type ReconnectStatus = "reconnecting" | "reconnected" | "failed";

type Props = {
  status: ReconnectStatus;
  sessionId?: string;
};

const TITLE: Record<ReconnectStatus, string> = {
  reconnecting: "연결이 끊어졌습니다 — 재연결 시도 중",
  reconnected: "재연결됨",
  failed: "재연결에 실패했습니다",
};

const DESC: Record<ReconnectStatus, string> = {
  reconnecting:
    "네트워크가 일시적으로 끊어졌을 수 있습니다. 자동으로 재연결을 시도합니다.",
  reconnected: "이어서 진행합니다.",
  failed:
    "자동 재연결을 모두 시도했지만 연결하지 못했습니다. 진행 중이던 턴은 서버에서 계속 실행 중일 수 있습니다.",
};

export function ReconnectStatusCard({ status, sessionId }: Props) {
  const [retrying, setRetrying] = useState(false);

  const canRetry = status === "failed" && Boolean(sessionId);

  const handleRetry = async () => {
    if (!sessionId || retrying) return;
    setRetrying(true);
    try {
      const handler = getRoomEventHandler(sessionId);
      if (handler) {
        await resumeRoomRun(sessionId, handler);
      }
    } catch {
      /* handler already reports sse_disconnected/run_failed via events */
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div className={`reconnect-card reconnect-card--${status}`} role="status">
      <div className="reconnect-card__body">
        <span className="reconnect-card__title">{TITLE[status]}</span>
        <p className="reconnect-card__desc">{DESC[status]}</p>
      </div>
      {canRetry ? (
        <div className="reconnect-card__actions">
          <button
            type="button"
            className="btn btn--sm"
            disabled={retrying}
            onClick={() => void handleRetry()}
          >
            {retrying ? "재시도 중…" : "다시 시도"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
