import { useCallback, useEffect, useState } from "react";
import {
  fetchSessionRuntime,
  resumeMissionLoop,
  type MissionBoardPayload,
  type RuntimeSnapshot,
  type SessionDetail,
  type TurnBudgetPayload,
} from "../api/client";
import type { RoomTasksPayload } from "../api/client";
import type { PlanMetaView } from "../utils/planMeta";
import { workPlanMetaLine } from "../utils/planMeta";
import {
  WorkStatusBar,
  resolveWorkPhase,
  resolveWorkPhaseFromMission,
} from "./WorkStatusBar";
import { CollapsibleGlassPanel } from "./CollapsibleGlassPanel";
import { PlanExecutePanel } from "./PlanExecutePanel";
import { PluginPanel } from "./PluginPanel";
import { MissionOverviewSection } from "./MissionOverviewSection";
import { MissionBoardStrip } from "./MissionBoardStrip";
import { TurnBudgetSection } from "./TurnBudgetSection";
import { WisdomSearchPanel } from "./WisdomSearchPanel";
import { buildMissionOverviewView } from "../utils/missionOverviewView";
import { missionPauseAlertText } from "../utils/missionPauseCopy";
import { useLocale } from "../i18n/useLocale";
import type { PlanExecutionRecord } from "../api/client";

type Props = {
  sessionId: string;
  session: SessionDetail | null;
  planMd: string;
  planMeta: PlanMetaView;
  planStaleNotice?: string | null;
  workFocus?: "execute" | "plan" | null;
  onWorkFocusHandled?: () => void;
  synthesizing: boolean;
  running: boolean;
  runBusy: boolean;
  onSynthesizeNow: () => void;
  onPlanRefClick: (line: number) => void;
  onFocusTask: (taskId: string) => void;
  onFocusObjection: (id: string, actionIndex?: number) => void;
  onSessionUpdated: () => void;
  roomTasks: RoomTasksPayload | null;
  cursorReady: boolean;
  latestExecution?: PlanExecutionRecord | null;
  hasPendingExecution?: boolean;
  hasDryRunDiff?: boolean;
  workHookAlert?: { event: string; body: string; blocked: boolean } | null;
  onDismissWorkHookAlert?: () => void;
};

/** Work tab — stepper chrome, mission strip, plan/execute body. */
export function WorkPanel({
  sessionId,
  session,
  planMd,
  planMeta,
  planStaleNotice = null,
  workFocus = null,
  onWorkFocusHandled,
  synthesizing,
  running,
  runBusy,
  onSynthesizeNow,
  onPlanRefClick,
  onFocusTask,
  onFocusObjection,
  onSessionUpdated,
  roomTasks,
  cursorReady,
  latestExecution = null,
  hasPendingExecution = false,
  hasDryRunDiff = false,
  workHookAlert = null,
  onDismissWorkHookAlert,
}: Props) {
  const { locale } = useLocale();
  const ko = locale === "ko";
  const missionOverview = buildMissionOverviewView({
    run: session?.run,
    planMd,
  });
  const showMissionStrip =
    missionOverview.enabled || Boolean(missionOverview.goalText);
  const hasPlan = Boolean(planMd.trim());
  const disabled = running || synthesizing || runBusy;
  const showPlanStalePanel = Boolean(planStaleNotice);
  const showSyncFailedBar =
    Boolean(planMeta.pendingAgreement) && !showPlanStalePanel;
  const [runtime, setRuntime] = useState<RuntimeSnapshot | null>(null);
  const missionLoop = session?.run?.mission_loop as
    | {
        enabled?: boolean;
        phase?: string;
        pause_reason?: string | null;
        circuit_breaker?: boolean;
        circuit_breaker_reason?: string | null;
        last_partial?: { resume_phase?: string } | null;
      }
    | undefined;
  const [resumeBusy, setResumeBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void fetchSessionRuntime(sessionId)
      .then((payload) => {
        if (!cancelled) setRuntime(payload);
      })
      .catch(() => {
        if (!cancelled) setRuntime(null);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, session?.run]);

  const missionPaused =
    runtime?.mission.paused ?? missionLoop?.phase === "MISSION_PAUSED";
  const handleMissionResume = useCallback(async () => {
    if (!missionPaused || resumeBusy) return;
    setResumeBusy(true);
    try {
      const resumePhase =
        runtime?.boulder?.resume_phase ??
        runtime?.mission.resume_phase ??
        missionLoop?.last_partial?.resume_phase ??
        "EXECUTE_QUEUE";
      await resumeMissionLoop(sessionId, resumePhase);
      onSessionUpdated();
      const nextRuntime = await fetchSessionRuntime(sessionId);
      setRuntime(nextRuntime);
    } finally {
      setResumeBusy(false);
    }
  }, [
    missionLoop?.last_partial?.resume_phase,
    missionPaused,
    onSessionUpdated,
    resumeBusy,
    runtime?.boulder?.resume_phase,
    runtime?.mission.resume_phase,
    sessionId,
  ]);
  const legacyWorkPhase =
    resolveWorkPhaseFromMission(
      missionLoop?.phase,
      missionLoop?.last_partial?.resume_phase,
    ) ??
    resolveWorkPhase({
      hasPlan,
      hasPendingExecution,
      hasDryRunDiff,
      pendingAgreement: Boolean(planMeta.pendingAgreement),
      latestExecution,
    });
  const workPhase = runtime?.work_phase ?? legacyWorkPhase;
  const metaLine = workPlanMetaLine(planMeta);
  const turnBudget: TurnBudgetPayload | undefined =
    runtime?.turn_budget ??
    (session?.run?.turn_budget as TurnBudgetPayload | undefined);
  const missionBoard: MissionBoardPayload | undefined =
    runtime?.mission_board ??
    (session?.run?.mission_board as MissionBoardPayload | undefined);
  const budgetPct = turnBudget?.budget_pct ?? 0;

  useEffect(() => {
    if (!workFocus) return;
    const id =
      workFocus === "execute" ? "work-execute-queue" : "work-plan-review";
    window.setTimeout(() => {
      document
        .getElementById(id)
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
      onWorkFocusHandled?.();
    }, 80);
  }, [workFocus, onWorkFocusHandled]);

  if (!hasPlan) {
    return (
      <div className="work-surface">
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
              <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
              <path d="M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2" />
              <path d="M9 12h6M9 16h4" />
            </svg>
          </span>
          <span className="empty-state__title">plan.md 없음</span>
          <span className="empty-state__hint">
            Transcript에서 토론을 시작하거나 「지금 정리」로 plan을 만드세요.
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="work-stack">
      <div className="work-surface work-surface--chrome work-chrome">
        <WorkStatusBar
          phase={workPhase}
          metaLine={metaLine || null}
          hasPlan={hasPlan}
          missionPaused={missionPaused}
          budgetPct={budgetPct}
        />

        <MissionBoardStrip board={missionBoard ?? null} ko={ko} />
        <TurnBudgetSection budget={turnBudget ?? null} ko={ko} />
        <WisdomSearchPanel
          sessionId={sessionId}
          index={runtime?.wisdom_index ?? null}
          ko={ko}
        />

        {missionPaused ? (
          <div className="work-alert work-alert--pause" role="status">
            <p className="work-alert__text">
              {missionPauseAlertText({
                ko,
                pauseReason:
                  runtime?.mission.pause_reason ?? missionLoop?.pause_reason,
                circuitBreaker:
                  runtime?.mission.circuit_breaker ??
                  missionLoop?.circuit_breaker,
                circuitBreakerReason:
                  runtime?.mission.circuit_breaker_reason ??
                  missionLoop?.circuit_breaker_reason,
                resumePhase:
                  runtime?.boulder?.resume_phase ??
                  runtime?.mission.resume_phase ??
                  missionLoop?.last_partial?.resume_phase,
                lastFailureReason: runtime?.last_failure?.reason,
              })}
            </p>
            <button
              type="button"
              className="plan-btn plan-btn--primary plan-btn--compact"
              disabled={disabled || resumeBusy}
              onClick={() => void handleMissionResume()}
            >
              {resumeBusy
                ? ko
                  ? "재개 중…"
                  : "Resuming…"
                : ko
                  ? "미션 재개"
                  : "Resume mission"}
            </button>
          </div>
        ) : null}

        {showMissionStrip ? (
          <MissionOverviewSection
            variant="work"
            view={missionOverview}
            ko={ko}
            onFocusBlock={onFocusObjection}
          />
        ) : null}

        <CollapsibleGlassPanel
          className="work-setup"
          title={ko ? "실행 설정" : "Execute setup"}
          summary={ko ? "Plugins · MCP allowlist" : "Plugins · MCP allowlist"}
          defaultOpen={false}
        >
          <PluginPanel sessionId={sessionId} compact disabled={disabled} />
        </CollapsibleGlassPanel>
      </div>

      {showPlanStalePanel ? (
        <div className="work-surface work-surface--alert work-plan-stale">
          <CollapsibleGlassPanel
            title="plan.md 변경됨"
            summary={planStaleNotice}
            variant="warn"
            defaultOpen
          >
            <p className="plan-stale">{planStaleNotice}</p>
          </CollapsibleGlassPanel>
        </div>
      ) : null}

      {showSyncFailedBar ? (
        <div className="work-surface work-surface--alert">
          <div className="plan-meta-bar plan-meta-bar--sync_failed">
            <p className="plan-meta-bar__line">{planMeta.freshnessLabel}</p>
            <button
              type="button"
              className="plan-btn plan-btn--primary"
              disabled={disabled}
              onClick={onSynthesizeNow}
            >
              {synthesizing ? "정리 중…" : "다시 정리"}
            </button>
          </div>
        </div>
      ) : null}

      <PlanExecutePanel
        sessionId={sessionId}
        planMd={planMd}
        run={session?.run}
        linkedTasks={roomTasks?.tasks}
        cursorReady={cursorReady}
        disabled={disabled}
        mergeChecks={runtime?.merge_checks ?? null}
        evidenceEntries={runtime?.evidence?.entries ?? []}
        onChatRefClick={onPlanRefClick}
        onFocusTask={onFocusTask}
        onFocusObjection={onFocusObjection}
        onUpdated={onSessionUpdated}
        workHookAlert={workHookAlert}
        onDismissWorkHookAlert={onDismissWorkHookAlert}
      />
    </div>
  );
}
