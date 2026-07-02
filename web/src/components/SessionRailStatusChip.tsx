import { useState } from "react";
import type { AgentHealthRow } from "../api/client";
import { AgentHealthPanel } from "./AgentHealthPanel";

type Props = {
  apiOk: boolean;
  agents: AgentHealthRow[];
  loading?: boolean;
  probeBridgeFailed?: boolean;
  onRefresh?: () => void;
  onReconnectCursor?: () => void;
  onReconnectClaude?: () => void;
  onReconnectKimiWork?: () => void;
  onOpenSettings?: () => void;
  reconnecting?: boolean;
};

export function SessionRailStatusChip({
  apiOk,
  agents,
  loading,
  probeBridgeFailed,
  onRefresh,
  onReconnectCursor,
  onReconnectClaude,
  onReconnectKimiWork,
  onOpenSettings,
  reconnecting,
}: Props) {
  const [open, setOpen] = useState(false);
  const readyCount = agents.filter((a) => a.ready).length;
  const issueCount = agents.filter(
    (a) => !a.ready || a.loop_ready === false || a.loop_cost_blocked,
  ).length;

  const chipLabel = !apiOk
    ? "API offline"
    : issueCount > 0
      ? `${readyCount}/${agents.length} · ${issueCount}건`
      : `${readyCount}/${agents.length}`;

  return (
    <div className="rail-status">
      <button
        type="button"
        className={`rail-status__chip${open ? " is-open" : ""}${issueCount > 0 ? " rail-status__chip--warn" : ""}`}
        aria-expanded={open}
        aria-controls="rail-status-detail"
        onClick={() => setOpen((v) => !v)}
        title="에이전트 연결"
      >
        <span
          className={`dot dot--${apiOk && issueCount === 0 ? "ok" : issueCount > 0 ? "warn" : "danger"}${apiOk ? " dot--live" : ""}`}
          aria-hidden
        />
        <span>
          연결 <strong>{chipLabel}</strong>
        </span>
        <span className="rail-status__caret" aria-hidden>
          <svg
            viewBox="0 0 24 24"
            width="14"
            height="14"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.7}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m6 9 6 6 6-6" />
          </svg>
        </span>
      </button>
      {open ? (
        <div id="rail-status-detail" className="rail-status__panel">
          <AgentHealthPanel
            compact
            apiOk={apiOk}
            agents={agents}
            loading={loading}
            reconnecting={reconnecting}
            showBridgeSetupGuide={probeBridgeFailed}
            onRefresh={onRefresh}
            onReconnectCursor={onReconnectCursor}
            onReconnectClaude={onReconnectClaude}
            onReconnectKimiWork={onReconnectKimiWork}
          />
          {onOpenSettings ? (
            <button
              type="button"
              className="btn btn--sm btn--ghost rail-status__settings-link"
              onClick={onOpenSettings}
            >
              설정
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
