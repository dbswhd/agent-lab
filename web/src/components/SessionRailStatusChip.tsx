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
  reconnecting?: boolean;
};

export function SessionRailStatusChip({
  apiOk,
  agents,
  loading,
  sessionsDir,
  probeBridgeFailed,
  onRefresh,
  onReconnectCursor,
  reconnecting,
}: Props) {
  const [open, setOpen] = useState(false);
  const readyCount = agents.filter((a) => a.ready).length;

  return (
    <div className="session-rail-status">
      <button
        type="button"
        className="session-rail-status__chip"
        aria-expanded={open}
        aria-controls="session-rail-status-detail"
        onClick={() => setOpen((v) => !v)}
        title="에이전트·API 상태"
      >
        <span
          className={`agent-health-dot${apiOk ? " agent-health-dot--ok" : " agent-health-dot--bad"}`}
          aria-hidden
        />
        <span className="session-rail-status__label">
          {apiOk ? `${readyCount}/3 ready` : "API offline"}
        </span>
        <span className="session-rail-status__chev" aria-hidden>
          ›
        </span>
      </button>
      {open ? (
        <div id="session-rail-status-detail" className="session-rail-status__detail">
          <AgentHealthPanel
            apiOk={apiOk}
            agents={agents}
            loading={loading}
            reconnecting={reconnecting}
            showBridgeSetupGuide={probeBridgeFailed}
            onRefresh={onRefresh}
            onReconnectCursor={onReconnectCursor}
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
