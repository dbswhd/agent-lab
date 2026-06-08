import { Avatar } from "./Avatar";
import { agentLabel } from "../utils/transcript";
import type { LiveMsg } from "../run/runSessionRegistry";
import type { AgentRole } from "../utils/transcript";

type Props = {
  turnMessages: LiveMsg[];
  running: boolean;
  active: { agent: string; round: number } | null;
  onStop?: () => void;
  longRunning?: boolean;
  runLockStuck?: boolean;
  releasingLock?: boolean;
  onReleaseLock?: () => void;
};

function entryType(role: string): "tool" | "system" | "agent" {
  if (role === "system") return "system";
  if (role === "tool") return "tool";
  return "agent";
}

function formatTs(ts?: string): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts.slice(11, 19) || ts;
  return d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** Run tab — prototype `run-log` / `run-entry` presentation. */
export function RunLogPanel({
  turnMessages,
  running,
  active,
  onStop,
  longRunning,
  runLockStuck,
  releasingLock,
  onReleaseLock,
}: Props) {
  const entries = turnMessages.filter(
    (m) => !m.roundDivider && m.role !== "you" && m.body?.trim(),
  );

  return (
    <div className="run-log">
      <div className="run-log__head">
        <svg
          viewBox="0 0 24 24"
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.7}
          strokeLinecap="round"
          aria-hidden
        >
          <rect x="4" y="4" width="16" height="16" rx="2" />
          <path d="M9 9h6M9 13h6M9 17h4" />
        </svg>
        Run log
        {longRunning && running ? (
          <span className="badge badge--warn" style={{ marginLeft: 8 }}>
            long run
          </span>
        ) : null}
        {runLockStuck && onReleaseLock ? (
          <button
            type="button"
            className="plan-btn"
            style={{ marginLeft: "auto" }}
            disabled={releasingLock}
            onClick={onReleaseLock}
          >
            {releasingLock ? "해제 중…" : "실행 잠금 해제"}
          </button>
        ) : null}
        {running && onStop && !runLockStuck ? (
          <button
            type="button"
            className="plan-btn plan-btn--danger"
            style={{ marginLeft: "auto" }}
            onClick={onStop}
          >
            Stop
          </button>
        ) : null}
      </div>

      {entries.length === 0 && !running ? (
        <div className="empty-state">
          <span className="empty-state__icon" aria-hidden>
            <svg
              viewBox="0 0 24 24"
              width="24"
              height="24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              strokeLinecap="round"
            >
              <rect x="4" y="4" width="16" height="16" rx="2" />
              <path d="M9 9h6M9 13h6" />
            </svg>
          </span>
          <span className="empty-state__title">실행 중인 턴 없음</span>
          <span className="empty-state__hint">
            메시지를 보내면 에이전트 실행 로그가 여기에 표시됩니다.
          </span>
        </div>
      ) : null}

      {running && active && entries.length === 0 ? (
        <div className={`run-entry run-entry--agent`}>
          <span className="run-entry__ts">…</span>
          <Avatar role={active.agent as AgentRole} size={20} />
          <span className="run-entry__type run-entry__type--agent">▸</span>
          <span className="run-entry__text">
            {agentLabel(active.agent)} · R{active.round} 응답 대기 중…
          </span>
        </div>
      ) : null}

      {entries.map((m) => {
        const type = entryType(m.role);
        const agentRole =
          type === "agent" ? (m.role as AgentRole) : undefined;
        return (
          <div key={m.id} className={`run-entry run-entry--${type}`}>
            <span className="run-entry__ts">
              {formatTs((m as LiveMsg & { ts?: string }).ts)}
            </span>
            {agentRole ? <Avatar role={agentRole} label={m.label} size={20} /> : null}
            <span className={`run-entry__type run-entry__type--${type}`}>
              {type === "tool" ? "$" : type === "system" ? "✦" : "▸"}
            </span>
            <span className="run-entry__text">
              {m.label && type === "agent" ? `${m.label}: ` : ""}
              {m.body}
            </span>
          </div>
        );
      })}

      {!running && entries.length > 0 ? (
        <div className="run-log__done">
          <svg
            viewBox="0 0 16 16"
            width="13"
            height="13"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            aria-hidden
          >
            <path d="M2 8l4 4 8-8" />
          </svg>
          Turn complete
        </div>
      ) : null}
    </div>
  );
}
