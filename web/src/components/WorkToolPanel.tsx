import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchSessionRuntime,
  type PlanExecutionRecord,
  type PlanWorkflowRecord,
  type RuntimeSnapshot,
  type SessionDetail,
} from "../api/client";
import type { RoomTasksPayload } from "../api/client";
import type { PlanMetaView } from "../utils/planMeta";
import { workPlanMetaLine } from "../utils/planMeta";
import { buildWorkDecisionSummary } from "../utils/workDecisionSummary";
import type { WorkDecisionActionId } from "../utils/workDecisionTypes";
import {
  workDecisionActionElementId,
  workFocusElementId,
  type WorkFocusTarget,
} from "../utils/workFocusTargets";
import { resolveWorkPhase } from "../utils/workStatusPhase";
import { PlanExecutePanel } from "./PlanExecutePanel";
import { WorkDecisionPanel } from "./WorkDecisionPanel";
import {
  WorkPlanApprovalSection,
  type PlanApprovalHost,
} from "./WorkPlanApprovalSection";
import { WorkStatusBar } from "./WorkStatusBar";

export type { WorkFocusTarget } from "../utils/workFocusTargets";

type Props = {
  sessionId: string;
  session: SessionDetail | null;
  planMd: string;
  planMeta: PlanMetaView;
  planStaleNotice?: string | null;
  workFocus?: WorkFocusTarget | null;
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
  executeError?: string | null;
  planWorkflow?: PlanWorkflowRecord;
  planApproval?: PlanApprovalHost | null;
  onOpenTasks?: () => void;
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
  executeError = null,
  planWorkflow,
  planApproval = null,
  onOpenTasks,
  workHookAlert = null,
  onDismissWorkHookAlert,
}: Props) {
  const hasPlan = Boolean(planMd.trim());
  const disabled = running || synthesizing || runBusy;
  const showPlanStalePanel = Boolean(planStaleNotice);
  const showSyncFailedBar =
    Boolean(planMeta.pendingAgreement) && !showPlanStalePanel;
  const [runtime, setRuntime] = useState<RuntimeSnapshot | null>(null);
  const executions = useMemo(
    () => (session?.run?.executions as PlanExecutionRecord[] | undefined) ?? [],
    [session?.run],
  );
  const latestExecution = executions.length
    ? executions[executions.length - 1]
    : null;
  const workPhase =
    runtime?.work_phase ??
    resolveWorkPhase({
      hasPlan,
      hasPendingExecution: Boolean(runtime?.execute.has_pending),
      hasDryRunDiff: Boolean(runtime?.execute.has_dry_run_diff),
      pendingAgreement: Boolean(planMeta.pendingAgreement),
      latestExecution,
    });
  const decisionSummary = useMemo(
    () =>
      buildWorkDecisionSummary({
        hasPlan,
        planMeta,
        planStaleNotice,
        planWorkflow,
        verifiedLoopView: {
          loop: {},
          proposedGoal: "",
          completionPromise: "DONE",
          criteria: "",
          pendingApproval: false,
          isDone: false,
          isFailed: false,
        },
        runtime,
        executions,
        mergeChecks: runtime?.merge_checks ?? null,
        workHookAlert,
        roomTasks,
      }),
    [
      executions,
      hasPlan,
      planMeta,
      planStaleNotice,
      planWorkflow,
      roomTasks,
      runtime,
      workHookAlert,
    ],
  );

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
    const id = workFocusElementId(workFocus);
    window.setTimeout(() => {
      document
        .getElementById(id)
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
      onWorkFocusHandled?.();
    }, 80);
  }, [workFocus, onWorkFocusHandled]);

  const handleDecisionAction = useCallback(
    (actionId: WorkDecisionActionId) => {
      if (actionId === "open_tasks") {
        onOpenTasks?.();
        return;
      }
      const id = workDecisionActionElementId(actionId);
      document.getElementById(id)?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    },
    [onOpenTasks],
  );

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

  if (planApproval?.enabled) {
    return (
      <div className="work-stack work-stack--tool">
        <div className="work-surface work-surface--chrome work-chrome">
          <WorkStatusBar
            phase={workPhase}
            metaLine={workPlanMetaLine(planMeta)}
            hasPlan={hasPlan}
          />
        </div>
        {showPlanStalePanel ? (
          <div className="work-surface work-surface--alert work-plan-stale">
            <p className="plan-stale">{planStaleNotice}</p>
          </div>
        ) : null}
        <WorkPlanApprovalSection
          planMd={planMd}
          approval={planApproval}
          objections={roomTasks?.open_objections ?? []}
          blockedReason={
            planStaleNotice ??
            (planMeta.pendingAgreement ? planMeta.freshnessLabel : null)
          }
          onFocusObjection={onFocusObjection}
        />
      </div>
    );
  }

  return (
    <div className="work-stack work-stack--tool">
      <div className="work-surface work-surface--chrome work-chrome">
        <WorkStatusBar
          phase={workPhase}
          metaLine={workPlanMetaLine(planMeta)}
          hasPlan={hasPlan}
        />
        <WorkDecisionPanel
          summary={decisionSummary}
          onAction={handleDecisionAction}
        />
      </div>

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

      {executeError ? (
        <div className="work-surface work-surface--alert" role="alert">
          <strong>실행을 시작하지 못했습니다.</strong>
          <p className="plan-card__error">{executeError}</p>
          <p className="plan-card__muted">
            Plan 승인은 유지되었습니다. 아래 Dry-run으로 다시 실행할 수
            있습니다.
          </p>
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
