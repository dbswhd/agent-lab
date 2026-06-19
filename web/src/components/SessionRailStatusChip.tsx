import { useState } from "react";
import type { AgentHealthRow } from "../api/client";
import { AgentHealthPanel } from "./AgentHealthPanel";
import { ApiDiagnosticsBar } from "./ApiDiagnosticsBar";

type Props = {
  apiOk: boolean;
  agents: AgentHealthRow[];
  loading?: boolean;
  sessionsDir?: string | null;
  probeBridgeFailed?: boolean;
  onRefresh?: () => void;
  onReconnectCursor?: () => void;
  onReconnectClaude?: () => void;
  onReconnectKimiWork?: () => void;
  reconnecting?: boolean;
};

/**
 * Rebuilt rail status chip. Behavior preserved: expandable health/diagnostics,
 * ready count, api-offline state. New class system: `.rail-status`.
 */
export function SessionRailStatusChip({
  apiOk,
  agents,
  loading,
  sessionsDir,
  probeBridgeFailed,
  onRefresh,
  onReconnectCursor,
  onReconnectClaude,
  onReconnectKimiWork,
  reconnecting,
}: Props) {
  const [open, setOpen] = useState(false);
  const readyCount = agents.filter((a) => a.ready).length;

  return (
    <div className="rail-status">
      <button
        type="button"
        className={`rail-status__chip${open ? " is-open" : ""}`}
        aria-expanded={open}
        aria-controls="rail-status-detail"
        onClick={() => setOpen((v) => !v)}
        title="에이전트·API 상태"
      >
        <span
          className={`dot dot--${apiOk ? "ok" : "danger"}${apiOk ? " dot--live" : ""}`}
          aria-hidden
        />
        <span>
          팀 상태 ·{" "}
          <strong>{apiOk ? `${readyCount}/3 ready` : "API offline"}</strong>
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
          <p className="rail-status__panel-heading">에이전트 · API 상태</p>
          <AgentHealthPanel
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
          <ApiDiagnosticsBar
            apiOk={apiOk}
            sessionsDir={sessionsDir ?? null}
            probeBridgeFailed={probeBridgeFailed ?? false}
          />
        </div>
      ) : null}
    </div>
  );
}
