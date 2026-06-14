import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchContextPreview, type SessionDetail } from "../api/client";
import { agentLabel } from "../utils/transcript";
import type { ComposerTurnProfile } from "../utils/turnProfile";
import { resolveTurnSend } from "../utils/turnProfile";
import {
  formatBudgetLine,
  parseLastTurnContext,
  trimLevelLabel,
  type AgentContextMeta,
  LAYER_ORDER,
} from "../utils/contextMeta";
import { ContextLayerBars, ContextMetaStats } from "./ContextLayerBars";

type Props = {
  sessionId: string | null;
  session?: SessionDetail | null;
  selectedAgents: string[];
  turnProfile: ComposerTurnProfile;
  disabled?: boolean;
  onClose?: () => void;
  /** Settings page: hide sidebar chrome, use ctx-preview layout. */
  embedded?: boolean;
};

type Tab = "preview" | "last_turn";

export function ContextPreviewPanel({
  sessionId,
  session,
  selectedAgents,
  turnProfile,
  disabled,
  onClose,
  embedded = false,
}: Props) {
  const [tab, setTab] = useState<Tab>("preview");
  const [agent, setAgent] = useState("cursor");
  const [parallelRound, setParallelRound] = useState(1);
  const [payload, setPayload] = useState<string | null>(null);
  const [previewMeta, setPreviewMeta] = useState<AgentContextMeta | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedAgentsKey = selectedAgents.join("\0");
  const turnSend = useMemo(
    () => resolveTurnSend(turnProfile, selectedAgents),
    // selectedAgentsKey avoids re-resolve when parent passes a new array ref.
    [turnProfile, selectedAgentsKey, selectedAgents],
  );
  const { agents, reviewMode, agentRounds, consensusMode } = turnSend;
  const agentsKey = agents.join("\0");

  const lastTurnCtx = useMemo(
    () => parseLastTurnContext(session?.run),
    [session?.run],
  );

  const lastTurnAgents = lastTurnCtx?.agents ?? [];
  const [lastAgentIdx, setLastAgentIdx] = useState(0);
  const lastMeta = lastTurnAgents[lastAgentIdx] ?? null;

  useEffect(() => {
    if (agents.length > 0 && !agents.includes(agent)) {
      setAgent(agents[0]);
    }
  }, [agentsKey, agent]);

  useEffect(() => {
    if (lastAgentIdx >= lastTurnAgents.length) {
      setLastAgentIdx(0);
    }
  }, [lastTurnAgents.length, lastAgentIdx]);

  const maxRounds = consensusMode ? 12 : Math.max(agentRounds, 2);

  const loadPreview = useCallback(async () => {
    if (!sessionId || agents.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchContextPreview({
        sessionId,
        agent,
        parallelRound,
        reviewMode,
        agents,
      });
      setPayload(res.payload);
      setPreviewMeta((res.meta as AgentContextMeta) ?? null);
    } catch (e) {
      setError(String(e));
      setPayload(null);
      setPreviewMeta(null);
    } finally {
      setLoading(false);
    }
  }, [sessionId, agent, parallelRound, reviewMode, agentsKey, agents]);

  useEffect(() => {
    if (tab !== "preview") return;
    let cancelled = false;
    if (!sessionId || agents.length === 0) return;
    setLoading(true);
    setError(null);
    void fetchContextPreview({
      sessionId,
      agent,
      parallelRound,
      reviewMode,
      agents,
    })
      .then((res) => {
        if (cancelled) return;
        setPayload(res.payload);
        setPreviewMeta((res.meta as AgentContextMeta) ?? null);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(String(e));
        setPayload(null);
        setPreviewMeta(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tab, sessionId, agent, parallelRound, reviewMode, agentsKey, agents]);

  if (!sessionId) return null;

  const summary = lastTurnCtx?.summary;

  const controls = (
    <>
      <div
        className={
          embedded ? "ctx-preview__head" : "context-sidebar-panel__controls"
        }
      >
        <div className={embedded ? "ctx-preview__selectors" : undefined}>
          <label className={embedded ? undefined : "context-preview__field"}>
            {!embedded ? <span>에이전트</span> : null}
            <select
              className={embedded ? "ns-select" : undefined}
              value={agent}
              disabled={loading || disabled}
              onChange={(e) => setAgent(e.target.value)}
            >
              {agents.map((id) => (
                <option key={id} value={id}>
                  {agentLabel(id)}
                </option>
              ))}
            </select>
          </label>
          <label className={embedded ? undefined : "context-preview__field"}>
            {!embedded ? <span>라운드</span> : null}
            <select
              className={embedded ? "ns-select" : undefined}
              value={parallelRound}
              disabled={loading || disabled}
              onChange={(e) => setParallelRound(Number(e.target.value))}
            >
              {Array.from({ length: maxRounds }, (_, i) => i + 1).map((r) => (
                <option key={r} value={r}>
                  R{r}
                </option>
              ))}
            </select>
          </label>
        </div>
        {embedded && previewMeta ? (
          <span className="ctx-preview__total">
            ~{((previewMeta.layer_chars?.total ?? 0) / 1000).toFixed(1)}k chars
            ·{" "}
            <span className="badge badge--accent">
              {trimLevelLabel(previewMeta.trim_level)}
            </span>
          </span>
        ) : null}
        {!embedded ? (
          <button
            type="button"
            className="context-preview__refresh"
            disabled={loading || disabled}
            onClick={() => void loadPreview()}
          >
            {loading ? "…" : "↻"}
          </button>
        ) : null}
      </div>
      {error ? <div className="context-preview__error">{error}</div> : null}
      {previewMeta?.layer_chars ? (
        <div
          className={embedded ? "ctx-preview__layers" : "context-preview__viz"}
        >
          {!embedded ? (
            <p className="context-preview__meta" role="status">
              <span
                className={`context-trim-badge context-trim-badge--${previewMeta.trim_level ?? "ok"}`}
              >
                {trimLevelLabel(previewMeta.trim_level)}
              </span>
              {" · "}
              {formatBudgetLine(previewMeta)}
            </p>
          ) : null}
          {!embedded ? <ContextMetaStats meta={previewMeta} /> : null}
          {embedded ? (
            <>
              {LAYER_ORDER.map((key) => {
                const chars = previewMeta.layer_chars?.[key];
                if (!chars) return null;
                const total = previewMeta.layer_chars?.total ?? 1;
                const pct = Math.round((chars / total) * 100);
                return (
                  <div key={key} className="ctx-preview__layer">
                    <span className="ctx-preview__layer-name">{key}</span>
                    <div className="ctx-preview__bar-wrap">
                      <div
                        className="ctx-preview__bar"
                        style={{ width: `${Math.max(4, pct)}%` }}
                      />
                    </div>
                    <span className="ctx-preview__chars">
                      {(chars / 1000).toFixed(1)}k
                    </span>
                  </div>
                );
              })}
            </>
          ) : (
            <ContextLayerBars
              layerChars={previewMeta.layer_chars}
              budgetPct={previewMeta.budget_pct}
              trimLevel={previewMeta.trim_level}
            />
          )}
        </div>
      ) : null}
    </>
  );

  if (embedded) {
    return <div className="ctx-preview__body">{controls}</div>;
  }

  return (
    <div className="context-sidebar-panel">
      <header className="context-sidebar-panel__head">
        <h3 className="context-sidebar-panel__title">컨텍스트</h3>
        {onClose ? (
          <button
            type="button"
            className="context-sidebar-panel__close"
            aria-label="컨텍스트 패널 닫기"
            onClick={onClose}
          >
            ×
          </button>
        ) : null}
      </header>

      <div className="context-sidebar-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "preview"}
          className={tab === "preview" ? "is-active" : ""}
          onClick={() => setTab("preview")}
        >
          미리보기
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "last_turn"}
          className={tab === "last_turn" ? "is-active" : ""}
          onClick={() => setTab("last_turn")}
          disabled={lastTurnAgents.length === 0}
        >
          마지막 턴
        </button>
      </div>

      {tab === "preview" ? (
        <>
          {controls}
          <pre className="context-sidebar-panel__payload">
            {payload ?? (loading ? "…" : "—")}
          </pre>
        </>
      ) : (
        <div className="context-preview__last-turn">
          {lastTurnAgents.length === 0 ? (
            <p className="context-preview__empty">
              아직 기록된 턴 컨텍스트가 없습니다. 토론을 한 번 실행하면 여기에
              레이어별 크기가 표시됩니다.
            </p>
          ) : (
            <>
              {summary ? (
                <p className="context-preview__meta" role="status">
                  <span
                    className={`context-trim-badge context-trim-badge--${summary.trim_level ?? "ok"}`}
                  >
                    {trimLevelLabel(summary.trim_level)}
                  </span>
                  {" · "}
                  최대 {summary.payload_chars_max?.toLocaleString() ?? "—"}{" "}
                  chars
                  {summary.any_turns_omitted ? " · 오래된 턴 생략" : ""}
                  {summary.any_chars_omitted ? " · 크기 trim" : ""}
                </p>
              ) : null}
              <label className="context-preview__field">
                <span>에이전트 호출</span>
                <select
                  value={lastAgentIdx}
                  onChange={(e) => setLastAgentIdx(Number(e.target.value))}
                >
                  {lastTurnAgents.map((a, i) => (
                    <option
                      key={`${a.agent}-r${a.parallel_round}-${i}`}
                      value={i}
                    >
                      {agentLabel(a.agent)} · R{a.parallel_round ?? 1}
                      {a.model ? ` · ${a.model}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              {lastMeta?.layer_chars ? (
                <div className="context-preview__viz">
                  <p className="context-preview__meta">
                    {formatBudgetLine(lastMeta)}
                  </p>
                  <ContextMetaStats meta={lastMeta} />
                  <ContextLayerBars
                    layerChars={lastMeta.layer_chars}
                    budgetPct={lastMeta.budget_pct}
                    trimLevel={lastMeta.trim_level}
                  />
                </div>
              ) : null}
            </>
          )}
        </div>
      )}
    </div>
  );
}
