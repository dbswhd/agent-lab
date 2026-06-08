import { useCallback, useEffect, useState } from "react";
import { resumeMissionLoop, type SessionDetail } from "../api/client";
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
import { buildMissionOverviewView } from "../utils/missionOverviewView";
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
};

/** Work tab — prototype `work-surface` + PlanExecutePanel only. */
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
}: Props) {
  const { locale } = useLocale();
  const ko = locale === "ko";
  const missionOverview = buildMissionOverviewView({
    run: session?.run,
    planMd,
  });
  const hasPlan = Boolean(planMd.trim());
  const disabled = running || synthesizing || runBusy;
  const showPlanStalePanel = Boolean(planStaleNotice);
  const showSyncFailedBar =
    Boolean(planMeta.pendingAgreement) && !showPlanStalePanel;
  const missionLoop = session?.run?.mission_loop as
    | {
        enabled?: boolean;
        phase?: string;
        current_action_index?: number | null;
        circuit_breaker?: boolean;
        wisdom_refs?: string[];
        pause_reason?: string | null;
        last_partial?: { resume_phase?: string } | null;
      }
    | undefined;
  const [resumeBusy, setResumeBusy] = useState(false);
  const missionPaused = missionLoop?.phase === "MISSION_PAUSED";
  const handleMissionResume = useCallback(async () => {
    if (!missionPaused || resumeBusy) return;
    setResumeBusy(true);
    try {
      const resumePhase =
        missionLoop?.last_partial?.resume_phase ?? "EXECUTE_QUEUE";
      await resumeMissionLoop(sessionId, resumePhase);
      onSessionUpdated();
    } finally {
      setResumeBusy(false);
    }
  }, [
    missionLoop?.last_partial?.resume_phase,
    missionPaused,
    onSessionUpdated,
    resumeBusy,
    sessionId,
  ]);
  const workPhase =
    resolveWorkPhaseFromMission(missionLoop?.phase) ??
    resolveWorkPhase({
      hasPlan,
      hasPendingExecution,
      hasDryRunDiff,
      pendingAgreement: Boolean(planMeta.pendingAgreement),
      latestExecution,
    });
  const wisdomFileCount = missionLoop?.wisdom_refs?.length ?? 0;
  const missionMeta =
    missionLoop?.enabled && missionLoop.phase
      ? [
          `Mission ${missionLoop.phase}`,
          missionLoop.current_action_index != null
            ? `action #${missionLoop.current_action_index}`
            : null,
          missionLoop.circuit_breaker ? "circuit breaker" : null,
          missionPaused ? "paused" : null,
          missionLoop.pause_reason ? String(missionLoop.pause_reason) : null,
          wisdomFileCount > 0 ? `notepad ×${wisdomFileCount}` : null,
        ]
          .filter(Boolean)
          .join(" · ")
      : null;
  const metaLine = missionMeta ?? workPlanMetaLine(planMeta);

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
      <div className="work-surface work-surface--chrome">
        <WorkStatusBar
          phase={workPhase}
          metaLine={metaLine}
          hasPlan={hasPlan}
        />
        {missionPaused ? (
          <div className="plan-meta-bar plan-meta-bar--sync_failed">
            <p className="plan-meta-bar__line">
              Mission paused — open execution cleaned up when possible.
            </p>
            <button
              type="button"
              className="plan-btn plan-btn--primary"
              disabled={disabled || resumeBusy}
              onClick={() => void handleMissionResume()}
            >
              {resumeBusy ? "재개 중…" : "Mission 재개"}
            </button>
          </div>
        ) : null}
        {missionOverview.enabled ? (
          <MissionOverviewSection
            view={missionOverview}
            ko={ko}
            onFocusBlock={onFocusObjection}
          />
        ) : null}
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
      <div className="work-surface">
        <CollapsibleGlassPanel
          title="Execute plugins"
          summary="Session MCP / plugin allowlist for execute & repair"
          defaultOpen={false}
        >
          <PluginPanel sessionId={sessionId} compact disabled={disabled} />
        </CollapsibleGlassPanel>
      </div>
      <PlanExecutePanel
        sessionId={sessionId}
        run={session?.run}
        linkedTasks={roomTasks?.tasks}
        cursorReady={cursorReady}
        disabled={disabled}
        onChatRefClick={onPlanRefClick}
        onFocusTask={onFocusTask}
        onFocusObjection={onFocusObjection}
        onUpdated={onSessionUpdated}
      />
    </div>
  );
}
