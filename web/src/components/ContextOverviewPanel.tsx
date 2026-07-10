import { useCallback, useEffect, useState } from "react";
import {
  fetchContextLayers,
  patchContextLayers,
  type AgentHealthRow,
  type MissionBoardPayload,
  type SessionDetail,
  type TurnBudgetPayload,
} from "../api/client";
import { useLocale } from "../i18n/useLocale";
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
import { GateProfileChips } from "./GateProfileChips";
import { RoutingDiagnostics } from "./RoutingDiagnostics";
import { useSessionRuntime } from "../hooks/useSessionRuntime";

type Props = {
  session: SessionDetail | null;
  sessionId: string | null;
  // healthAgents/goalView are accepted for API compatibility but rendered
  // elsewhere now (SessionRailStatusChip / GoalLoopBanner) — see Overview de-dup.
  healthAgents: AgentHealthRow[];
  goalView: GoalLoopView;
  planMeta: PlanMetaView;
  onFocusObjection?: (id: string, actionIndex?: number) => void;
};

type LayerToggles = {
  mission_wisdom: boolean;
  repo_tree: boolean;
};

function layerTogglesFromResponse(
  layers: Record<string, boolean> | undefined,
): LayerToggles {
  return {
    mission_wisdom: layers?.mission_wisdom ?? true,
    repo_tree: layers?.repo_tree ?? true,
  };
}

function mergeLayerToggles(
  prev: LayerToggles,
  layers: Record<string, boolean> | undefined,
): LayerToggles {
  if (!layers) return prev;
  return {
    mission_wisdom: layers.mission_wisdom ?? prev.mission_wisdom,
    repo_tree: layers.repo_tree ?? prev.repo_tree,
  };
}

/** Context sidebar — Overview tab (prototype `ContextSidebar`). */
export function ContextOverviewPanel({
  session,
  sessionId,
  planMeta,
  onFocusObjection,
}: Props) {
  const { locale } = useLocale();
  const ko = locale === "ko";
  const missionView = buildMissionOverviewView({
    run: session?.run,
    planMd: session?.plan_md,
  });
  const [layerToggles, setLayerToggles] = useState<LayerToggles>({
    mission_wisdom: true,
    repo_tree: true,
  });
  const [layerBusy, setLayerBusy] = useState(false);
  const { runtime: diagnosticsRuntime } = useSessionRuntime(sessionId, {
    run: session?.run,
  });

  useEffect(() => {
    const runLayers = (
      session?.run as { context_layers?: Record<string, boolean> } | undefined
    )?.context_layers;
    if (runLayers) {
      setLayerToggles((prev) => mergeLayerToggles(prev, runLayers));
      return;
    }
    if (!sessionId) return;
    void fetchContextLayers(sessionId)
      .then((res) => {
        if (res.context_layers) {
          setLayerToggles(layerTogglesFromResponse(res.context_layers));
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
          setLayerToggles(layerTogglesFromResponse(res.context_layers));
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
  const planStatusLine = [planMeta.triggerLabel, planMeta.timeLabel]
    .filter(Boolean)
    .join(" · ");

  // Layers the human actually controls (kept in the main panel).
  const LAYER_TOGGLES = [
    {
      id: "mission_wisdom" as const,
      label: ko ? "미션 메모" : "Mission wisdom",
      meta: "notepad",
      on: layerToggles.mission_wisdom,
    },
    {
      id: "repo_tree" as const,
      label: ko ? "저장소 트리" : "Repo tree",
      meta: "workspace",
      on: layerToggles.repo_tree,
    },
  ];

  // Derived "is it included" status — diagnostic, not user-managed.
  const LAYER_STATUS = [
    {
      id: "plan",
      label: "plan.md",
      meta: "plan",
      on: Boolean(session?.plan_md?.trim()),
    },
    {
      id: "chat",
      label: "chat.jsonl",
      meta: `${session?.chat?.length ?? 0} ${ko ? "턴" : "turns"}`,
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
        board={
          (session?.run?.mission_board as MissionBoardPayload | undefined) ??
          null
        }
        ko={ko}
      />

      {planMeta.lastUpdate ? (
        <section className="ctx-section">
          <div className="ctx-section__label">Plan</div>
          <div
            className={`ctx-plan-status ctx-plan-status--${planMeta.freshness}`}
          >
            <span className="ctx-plan-status__label">
              {planMeta.freshnessLabel}
            </span>
            {planStatusLine ? (
              <span className="ctx-plan-status__meta">{planStatusLine}</span>
            ) : null}
            {planMeta.reviewTurnLabel ? (
              <span className="ctx-plan-status__meta">
                {planMeta.reviewTurnLabel}
              </span>
            ) : null}
            {planMeta.turnRolesLabel ? (
              <span className="ctx-plan-status__meta">
                {planMeta.turnRolesLabel}
              </span>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className="ctx-section">
        <div className="ctx-section__label">
          {ko ? "컨텍스트 레이어" : "Context layers"}
        </div>
        <ul className="ctx-layers">
          {LAYER_TOGGLES.map((layer) => (
            <li key={layer.id} className="ctx-layers__row">
              <span className="ctx-layers__name">{layer.label}</span>
              <span className="ctx-layers__meta">{layer.meta}</span>
              <button
                type="button"
                className={`ctx-layers__toggle${layer.on ? " is-on" : ""}`}
                disabled={layerBusy || !sessionId}
                aria-pressed={layer.on}
                onClick={() => void toggleLayer(layer.id)}
              >
                {layer.on ? "ON" : "OFF"}
              </button>
            </li>
          ))}
        </ul>
      </section>

      <details className="ctx-diagnostics">
        <summary className="ctx-diagnostics__summary">
          {ko ? "진단" : "Diagnostics"}
        </summary>
        <div className="ctx-diagnostics__body">
          <GateProfileChips
            sessionId={sessionId}
            runtimeSnapshot={diagnosticsRuntime}
          />

          <RoutingDiagnostics
            sessionId={sessionId}
            run={session?.run as Record<string, unknown> | undefined}
            runtimeSnapshot={diagnosticsRuntime}
          />

          <section className="ctx-section">
            <div className="ctx-section__label">
              {ko ? "포함된 컨텍스트" : "Included context"}
            </div>
            <ul className="ctx-layers">
              {LAYER_STATUS.map((layer) => (
                <li key={layer.id} className="ctx-layers__row">
                  <span className="ctx-layers__name">{layer.label}</span>
                  <span className="ctx-layers__meta">{layer.meta}</span>
                  <span
                    className={`ctx-layers__state${layer.on ? " is-on" : ""}`}
                    aria-label={layer.on ? "included" : "empty"}
                  >
                    {layer.on ? "ON" : "—"}
                  </span>
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

          <TurnBudgetSection
            budget={
              (session?.run?.turn_budget as TurnBudgetPayload | undefined) ??
              null
            }
            ko={ko}
          />
        </div>
      </details>
    </div>
  );
}
