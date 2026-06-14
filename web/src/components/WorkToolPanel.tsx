import { useEffect, useState } from "react";
import {
  fetchSessionRuntime,
  type RuntimeSnapshot,
  type SessionDetail,
} from "../api/client";
import type { RoomTasksPayload } from "../api/client";
import type { PlanMetaView } from "../utils/planMeta";
import { PlanExecutePanel } from "./PlanExecutePanel";

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
  workHookAlert?: {
    readonly event: string;
    readonly body: string;
    readonly blocked: boolean;
  } | null;
  onDismissWorkHookAlert?: () => void;
};

/** Tools > Work — execute-focused surface without Mission OS duplicates. */
export function WorkToolPanel({
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
  workHookAlert = null,
  onDismissWorkHookAlert,
}: Props) {
  const hasPlan = Boolean(planMd.trim());
  const disabled = running || synthesizing || runBusy;
  const showPlanStalePanel = Boolean(planStaleNotice);
  const showSyncFailedBar =
    Boolean(planMeta.pendingAgreement) && !showPlanStalePanel;
  const [runtime, setRuntime] = useState<RuntimeSnapshot | null>(null);

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
      <div className="work-surface tools-work-empty">
        <div className="empty-state">
          <span className="empty-state__title">plan.md 없음</span>
          <span className="empty-state__hint">
            Transcript에서 토론을 시작하거나 plan을 먼저 만드세요.
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="work-stack work-stack--tool">
      {showPlanStalePanel ? (
        <div className="work-surface work-surface--alert work-plan-stale">
          <p className="plan-stale">{planStaleNotice}</p>
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
