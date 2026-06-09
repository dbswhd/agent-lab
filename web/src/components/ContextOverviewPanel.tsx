import { useCallback, useEffect, useState } from "react";
import {
  fetchContextLayers,
  patchContextLayers,
  type AgentHealthRow,
  type MissionBoardPayload,
  type SessionDetail,
  type TurnBudgetPayload,
} from "../api/client";
import { Avatar } from "./Avatar";
import { useLocale } from "../i18n/useLocale";
import type { AgentRole } from "../utils/transcript";
import { agentLabel } from "../utils/transcript";
import {
  parseLastTurnContext,
  trimLevelLabel,
  formatBudgetLine,
} from "../utils/contextMeta";
import { ContextLayerBars } from "./ContextLayerBars";
import type { PlanMetaView } from "../utils/planMeta";
import type { GoalLoopView } from "../utils/goalLoopView";
import { buildMissionOverviewView } from "../utils/missionOverviewView";
import { MissionOverviewSection } from "./MissionOverviewSection";
import { TurnBudgetSection } from "./TurnBudgetSection";
import { MissionBoardStrip } from "./MissionBoardStrip";

type Props = {
  session: SessionDetail | null;
  sessionId: string | null;
  healthAgents: AgentHealthRow[];
  goalView: GoalLoopView;
  planMeta: PlanMetaView;
  onFocusObjection?: (id: string, actionIndex?: number) => void;
};

function OracleStatusBadge({ loop }: { loop: GoalLoopView["loop"] }) {
  if (!loop.status) return null;
  const achieved = loop.status === "achieved";
  const failed = loop.last_check?.verdict === "fail";
  const cls = achieved ? "ok" : failed ? "fail" : "progress";
  const label = achieved ? "목표 달성" : failed ? "Oracle FAIL" : "진행 중";
  return (
    <span className={`ctx-oracle-badge ctx-oracle-badge--${cls}`}>{label}</span>
  );
}

/** Context sidebar — Overview tab (prototype `ContextSidebar`). */
export function ContextOverviewPanel({
  session,
  sessionId,
  healthAgents,
  goalView,
  planMeta,
  onFocusObjection,
}: Props) {
  const { locale } = useLocale();
  const ko = locale === "ko";
  const missionView = buildMissionOverviewView({
    run: session?.run,
    planMd: session?.plan_md,
  });
  const [layerToggles, setLayerToggles] = useState({
    mission_wisdom: true,
    repo_tree: true,
  });
  const [layerBusy, setLayerBusy] = useState(false);

  useEffect(() => {
    const runLayers = (
      session?.run as { context_layers?: Record<string, boolean> } | undefined
    )?.context_layers;
    if (runLayers) {
      setLayerToggles((prev) => ({
        mission_wisdom:
          runLayers.mission_wisdom ?? prev.mission_wisdom,
        repo_tree: runLayers.repo_tree ?? prev.repo_tree,
      }));
      return;
    }
    if (!sessionId) return;
    void fetchContextLayers(sessionId)
      .then((res) => {
        if (res.context_layers) {
          setLayerToggles({
            mission_wisdom: res.context_layers.mission_wisdom ?? true,
            repo_tree: res.context_layers.repo_tree ?? true,
          });
        }
      })
      .catch(() => {});
  }, [session?.run, sessionId]);

  const toggleLayer = useCallback(
    async (key: "mission_wisdom" | "repo_tree") => {
      if (!sessionId || layerBusy) return;
      const next = !layerToggles[key];
      setLayerToggles((prev) => ({ ...prev, [key]: next }));
      setLayerBusy(true);
      try {
        const res = await patchContextLayers(sessionId, { [key]: next });
        if (res.context_layers) {
          setLayerToggles({
            mission_wisdom: res.context_layers.mission_wisdom ?? true,
            repo_tree: res.context_layers.repo_tree ?? true,
          });
        }
      } catch {
        setLayerToggles((prev) => ({ ...prev, [key]: !next }));
      } finally {
        setLayerBusy(false);
      }
    },
    [layerBusy, layerToggles, sessionId],
  );

  const lastTurnCtx = parseLastTurnContext(session?.run);
  const topAgent = lastTurnCtx?.agents?.[0] ?? null;
  const hasGoal = Boolean(goalView.goal.text);
  const planStatusLine = [planMeta.triggerLabel, planMeta.timeLabel]
    .filter(Boolean)
    .join(" · ");

  const LAYERS = [
    {
      id: "mission_wisdom",
      label: ko ? "미션 메모" : "Mission wisdom",
      meta: ko ? "notepad" : "notepad",
      on: layerToggles.mission_wisdom,
      toggle: true as const,
    },
    {
      id: "repo_tree",
      label: ko ? "저장소 트리" : "Repo tree",
      meta: ko ? "workspace" : "workspace",
      on: layerToggles.repo_tree,
      toggle: true as const,
    },
    { id: "plan", label: "plan.md", meta: ko ? "plan" : "plan", on: Boolean(session?.plan_md?.trim()) },
    {
      id: "chat",
      label: "chat.jsonl",
      meta: ko
        ? `${session?.chat?.length ?? 0} 턴`
        : `${session?.chat?.length ?? 0} turns`,
      on: (session?.chat?.length ?? 0) > 0,
    },
    {
      id: "files",
      label: ko ? "첨부 파일" : "Attached files",
      meta: String(session?.attachments?.length ?? 0),
      on: (session?.attachments?.length ?? 0) > 0,
    },
  ];

  return (
    <div className="ctx-overview">
      <MissionOverviewSection
        view={missionView}
        ko={ko}
        onFocusBlock={onFocusObjection}
      />

      <MissionBoardStrip
        board={(session?.run?.mission_board as MissionBoardPayload | undefined) ?? null}
        ko={ko}
      />
      <TurnBudgetSection
        budget={(session?.run?.turn_budget as TurnBudgetPayload | undefined) ?? null}
        ko={ko}
      />

      <section className="ctx-section">
        <div className="ctx-section__label">{ko ? "세션 목표" : "Session goal"}</div>
        <div className="ctx-overview__goal-row">
          {hasGoal ? (
            <p className="ctx-goal">{goalView.goal.text}</p>
          ) : (
            <p className="ctx-overview__empty">
              {ko ? "목표 미설정 — Tasks 탭에서 설정" : "No goal — set in Tasks tab"}
            </p>
          )}
          <OracleStatusBadge loop={goalView.loop} />
        </div>
        {goalView.loop.last_check?.detail ? (
          <p className="ctx-overview__detail">{goalView.loop.last_check.detail}</p>
        ) : null}
      </section>

      {planMeta.lastUpdate ? (
        <section className="ctx-section">
          <div className="ctx-section__label">Plan</div>
          <div className={`ctx-plan-status ctx-plan-status--${planMeta.freshness}`}>
            <span className="ctx-plan-status__label">{planMeta.freshnessLabel}</span>
            {planStatusLine ? (
              <span className="ctx-plan-status__meta">{planStatusLine}</span>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className="ctx-section">
        <div className="ctx-section__label">
          {ko ? "컨텍스트 레이어" : "Context layers"}
        </div>
        <ul className="ctx-layers">
          {LAYERS.map((layer) => (
            <li key={layer.id} className="ctx-layers__row">
              <span className="ctx-layers__name">{layer.label}</span>
              <span className="ctx-layers__meta">{layer.meta}</span>
              {"toggle" in layer && layer.toggle && sessionId ? (
                <button
                  type="button"
                  className={`ctx-layers__toggle${layer.on ? " is-on" : ""}`}
                  disabled={layerBusy}
                  aria-pressed={layer.on}
                  onClick={() =>
                    void toggleLayer(layer.id as "mission_wisdom" | "repo_tree")
                  }
                >
                  {layer.on ? "ON" : "OFF"}
                </button>
              ) : (
                <span
                  className={`ctx-layers__state${layer.on ? " is-on" : ""}`}
                  aria-label={layer.on ? "included" : "empty"}
                >
                  {layer.on ? "ON" : "—"}
                </span>
              )}
            </li>
          ))}
        </ul>
      </section>

      {topAgent?.layer_chars ? (
        <section className="ctx-section">
          <div className="ctx-section__label">
            {ko ? "마지막 턴 컨텍스트" : "Last turn context"}
            <span className="ctx-section__label-meta">
              {agentLabel(topAgent.agent)} · R{topAgent.parallel_round ?? 1}
            </span>
          </div>
          <p className="ctx-overview__budget">
            <span
              className={`context-trim-badge context-trim-badge--${topAgent.trim_level ?? "ok"}`}
            >
              {trimLevelLabel(topAgent.trim_level)}
            </span>
            {" · "}
            {formatBudgetLine(topAgent)}
          </p>
          <ContextLayerBars
            layerChars={topAgent.layer_chars}
            budgetPct={topAgent.budget_pct}
            trimLevel={topAgent.trim_level}
          />
        </section>
      ) : null}

      {healthAgents.length > 0 ? (
        <section className="ctx-section">
          <div className="ctx-section__label">{ko ? "팀" : "Team"}</div>
          <div className="ctx-team">
            {healthAgents.map((h) => (
              <div key={h.id} className="ctx-agent">
                <Avatar role={h.id as AgentRole} label={h.label} size={20} />
                <span className="ctx-agent__name">{h.label}</span>
                {h.model ? (
                  <span className="ctx-agent__model">{h.model}</span>
                ) : null}
                <span
                  className={`dot dot--${h.ready ? "ok" : "warn"}`}
                  aria-hidden
                />
                <span
                  className={`ctx-agent__status ctx-agent__status--${h.ready ? "ok" : "warn"}`}
                >
                  {h.ready ? "Ready" : ko ? "오프라인" : "Offline"}
                </span>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
