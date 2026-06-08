import { useEffect } from "react";
import type { SessionDetail } from "../api/client";
import type { RoomTasksPayload } from "../api/client";
import type { PlanMetaView } from "../utils/planMeta";
import { workPlanMetaLine } from "../utils/planMeta";
import { WorkStatusBar, resolveWorkPhase } from "./WorkStatusBar";
import { CollapsibleGlassPanel } from "./CollapsibleGlassPanel";
import { PlanExecutePanel } from "./PlanExecutePanel";
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
  const hasPlan = Boolean(planMd.trim());
  const disabled = running || synthesizing || runBusy;
  const showPlanStalePanel = Boolean(planStaleNotice);
  const showSyncFailedBar =
    Boolean(planMeta.pendingAgreement) && !showPlanStalePanel;
  const workPhase = resolveWorkPhase({
    hasPlan,
    hasPendingExecution,
    hasDryRunDiff,
    pendingAgreement: Boolean(planMeta.pendingAgreement),
    latestExecution,
  });

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
          metaLine={workPlanMetaLine(planMeta)}
          hasPlan={hasPlan}
        />
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
