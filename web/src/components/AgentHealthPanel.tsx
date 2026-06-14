import { useState } from "react";
import type { AgentHealthRow } from "../api/client";

type Props = {
  apiOk: boolean;
  agents: AgentHealthRow[];
  loading?: boolean;
  onRefresh?: () => void;
  onReconnectCursor?: () => void;
  onReconnectClaude?: () => void;
  reconnecting?: boolean;
  /** Show bridge setup hint when probe_bridge=true failed for Cursor. */
  showBridgeSetupGuide?: boolean;
};

function bridgeLabel(row: AgentHealthRow): string | null {
  if (row.id !== "cursor") return null;
  const mode =
    row.bridge_mode === "external"
      ? "external bridge"
      : row.bridge_mode === "auto"
        ? "auto-launch"
        : null;
  if (row.bridge === "ok") return mode ? `${mode} · OK` : "bridge OK";
  if (row.bridge === "error") return mode ? `${mode} · 실패` : "bridge 실패";
  if (row.bridge === "unknown") return mode ?? "bridge 미확인";
  return mode;
}

function modelReadinessLabel(row: AgentHealthRow): string | null {
  if (row.loop_cost_blocked) return "Loop cost blocked";
  if (row.loop_ready) return "Loop-ready";
  if (row.team_ready) return "Team-ready";
  return null;
}

function costTierLabel(row: AgentHealthRow): string | null {
  if (!row.model_cost_tier) return null;
  return `cost ${row.model_cost_tier}`;
}

export function AgentHealthPanel({
  apiOk,
  agents,
  loading,
  onRefresh,
  onReconnectCursor,
  onReconnectClaude,
  reconnecting,
  showBridgeSetupGuide,
}: Props) {
  const [open, setOpen] = useState(false);
  const readyCount = agents.filter((a) => a.ready).length;
  const cursorRow = agents.find((a) => a.id === "cursor");
  const claudeRow = agents.find((a) => a.id === "claude");
  const showReconnect =
    Boolean(cursorRow?.configured && onReconnectCursor) &&
    (cursorRow?.bridge === "error" || !cursorRow?.ready);
  const showReconnectClaude =
    Boolean(claudeRow?.configured && onReconnectClaude) && !claudeRow?.ready;

  return (
    <div
      className={["agent-health-panel", open ? "agent-health-panel--open" : ""]
        .filter(Boolean)
        .join(" ")}
      aria-label="에이전트 상태"
    >
      <button
        type="button"
        className="agent-health-panel__toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="agent-health-panel__api">
          <span
            className={`agent-health-dot${apiOk ? " agent-health-dot--ok" : " agent-health-dot--bad"}`}
            aria-hidden
          />
          API {apiOk ? "8765" : "오프라인"}
        </span>
        <span className="agent-health-panel__summary">
          · {readyCount}/{agents.length} ready
        </span>
        {onRefresh ? (
          <button
            type="button"
            className="mac-btn-secondary mac-btn-icon agent-health-panel__refresh"
            disabled={loading || reconnecting}
            onClick={(e) => {
              e.stopPropagation();
              onRefresh();
            }}
            title="bridge 포함 재확인"
            aria-label="상태 새로고침"
          >
            {loading ? "…" : "↻"}
          </button>
        ) : null}
        <span className="agent-health-panel__chev" aria-hidden>
          ›
        </span>
      </button>
      {open ? (
        <>
          <ul className="agent-health-list">
            {agents.map((row) => {
              const bridge = bridgeLabel(row);
              const modelReadiness = modelReadinessLabel(row);
              const costTier = costTierLabel(row);
              return (
                <li
                  key={row.id}
                  className={[
                    "agent-health-row",
                    row.ready
                      ? "agent-health-row--ok"
                      : "agent-health-row--bad",
                  ].join(" ")}
                  title={row.hint ?? undefined}
                >
                  <span
                    className={`agent-health-dot${row.ready ? " agent-health-dot--ok" : " agent-health-dot--bad"}`}
                    aria-hidden
                  />
                  <span className="agent-health-row__label">{row.label}</span>
                  <span className="agent-health-row__meta">
                    {row.model_id
                      ? row.model_id
                      : row.model
                        ? row.model
                        : row.configured
                          ? "설정됨"
                          : "미설정"}
                    {bridge ? ` · ${bridge}` : ""}
                    {costTier ? ` · ${costTier}` : ""}
                    {modelReadiness ? ` · ${modelReadiness}` : ""}
                    {row.model_provider ? ` · ${row.model_provider}` : ""}
                  </span>
                  {row.id === "cursor" && showReconnect ? (
                    <button
                      type="button"
                      className="mac-btn-secondary mac-btn-secondary--compact agent-health-row__reconnect"
                      disabled={loading || reconnecting}
                      onClick={onReconnectCursor}
                    >
                      {reconnecting ? "재연결…" : "재연결"}
                    </button>
                  ) : null}
                  {row.id === "claude" && showReconnectClaude ? (
                    <button
                      type="button"
                      className="mac-btn-secondary mac-btn-secondary--compact agent-health-row__reconnect"
                      disabled={loading || reconnecting}
                      onClick={onReconnectClaude}
                    >
                      {reconnecting ? "재연결…" : "재연결"}
                    </button>
                  ) : null}
                  {row.hint && !row.ready ? (
                    <span className="agent-health-row__hint">{row.hint}</span>
                  ) : null}
                  {row.fallback && !row.ready ? (
                    <span className="agent-health-row__fallback">
                      fallback: {row.fallback}
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
          {showBridgeSetupGuide ? (
            <p className="agent-health-panel__setup-guide">
              Cursor bridge — <code>~/.agent-lab/.env</code>에{" "}
              <code>CURSOR_SDK_BRIDGE_BIN</code> 절대 경로.{" "}
              <code>pip install -e &quot;.[cursor]&quot;</code> ·
              docs/STABILITY.md
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
