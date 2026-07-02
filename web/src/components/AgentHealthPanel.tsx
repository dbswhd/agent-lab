import type { AgentHealthRow } from "../api/client";

type Props = {
  apiOk: boolean;
  agents: AgentHealthRow[];
  loading?: boolean;
  onRefresh?: () => void;
  onReconnectCursor?: () => void;
  onReconnectClaude?: () => void;
  onReconnectKimiWork?: () => void;
  reconnecting?: boolean;
  showBridgeSetupGuide?: boolean;
  compact?: boolean;
};

function statusLine(row: AgentHealthRow): string | null {
  if (!row.ready) return row.hint || "연결 필요";
  if (row.loop_cost_blocked) return "Loop 비용 초과";
  if (row.loop_ready === false) return row.hint || null;
  return null;
}

function rowTone(row: AgentHealthRow): "ok" | "warn" | "bad" {
  if (!row.ready) return "bad";
  if (row.loop_ready === false || row.loop_cost_blocked) return "warn";
  return "ok";
}

function rowAction(
  row: AgentHealthRow,
): { id: "cursor" | "claude" | "kimi_work"; label: string } | null {
  if (!row.configured) return null;
  if (row.id === "cursor" && (row.bridge === "error" || !row.ready)) {
    return { id: "cursor", label: "재연결" };
  }
  if (row.id === "claude" && !row.ready) {
    return { id: "claude", label: "재연결" };
  }
  if (
    row.id === "kimi_work" &&
    (!row.ready || row.bridge === "error" || row.loop_ready === false)
  ) {
    return { id: "kimi_work", label: "재연결" };
  }
  return null;
}

export function AgentHealthPanel({
  apiOk,
  agents,
  loading,
  onRefresh,
  onReconnectCursor,
  onReconnectClaude,
  onReconnectKimiWork,
  reconnecting,
  showBridgeSetupGuide,
  compact = false,
}: Props) {
  const issueCount = agents.filter((row) => rowTone(row) !== "ok").length;
  const visibleAgents = compact
    ? agents.filter((row) => rowTone(row) !== "ok")
    : agents;

  return (
    <div
      className={`team-health${compact ? " team-health--compact" : ""}`}
      aria-label="에이전트 연결 상태"
    >
      {!compact ? (
        <div className="team-health__toolbar">
          <span className="team-health__summary">
            {apiOk ? "API 연결됨" : "API 오프라인"}
            {issueCount > 0 ? ` · ${issueCount}건` : ""}
          </span>
          {onRefresh ? (
            <button
              type="button"
              className="btn btn--sm btn--ghost team-health__refresh"
              disabled={loading || reconnecting}
              onClick={onRefresh}
            >
              {loading ? "…" : "새로고침"}
            </button>
          ) : null}
        </div>
      ) : null}

      {compact && issueCount === 0 ? (
        <p className="team-health__all-ok">모든 에이전트 연결됨</p>
      ) : null}

      {visibleAgents.length > 0 ? (
        <ul className="team-health__list">
          {visibleAgents.map((row) => {
            const tone = rowTone(row);
            const detail = statusLine(row);
            const action = rowAction(row);

            return (
              <li
                key={row.id}
                className={`team-health__row team-health__row--${tone}`}
              >
                <span
                  className={`team-health__dot team-health__dot--${tone}`}
                  aria-hidden
                />
                <div className="team-health__row-body">
                  <span className="team-health__row-label">{row.label}</span>
                  {detail ? (
                    <span className="team-health__row-detail">{detail}</span>
                  ) : compact ? null : (
                    <span className="team-health__row-detail team-health__row-detail--muted">
                      {row.model_id || row.model || "준비됨"}
                    </span>
                  )}
                </div>
                {action ? (
                  <button
                    type="button"
                    className="btn btn--sm btn--ghost team-health__reconnect"
                    disabled={loading || reconnecting}
                    onClick={() => {
                      if (action.id === "cursor") onReconnectCursor?.();
                      else if (action.id === "claude") onReconnectClaude?.();
                      else onReconnectKimiWork?.();
                    }}
                  >
                    {reconnecting ? "…" : action.label}
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}

      {showBridgeSetupGuide ? (
        <p className="team-health__guide">
          Cursor bridge: <code>CURSOR_SDK_BRIDGE_BIN</code>
        </p>
      ) : null}
    </div>
  );
}
