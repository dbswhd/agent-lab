import { useCallback, useEffect, useMemo } from "react";
import {
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
import { hasPlanWorkflowClarifySurface } from "../utils/planWorkflowView";
import { useSessionRuntime } from "../hooks/useSessionRuntime";
import { PlanExecutePanel } from "./PlanExecutePanel";
import { WorkDecisionPanel } from "./WorkDecisionPanel";
import {
  WorkPlanApprovalSection,
  type PlanApprovalHost,
} from "./WorkPlanApprovalSection";
import { WorkStatusBar } from "./WorkStatusBar";
import { GjcPipelineBar } from "./GjcPipelineBar";
import { GjcExternalHandoffStrip } from "./GjcExternalHandoffStrip";
import {
  gjcPipelineMetaLine,
  resolveGjcPipelinePhase,
} from "../utils/gjcPipelinePhase";

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
  onOpenDiff?: () => void;
  onOpenFiles?: () => void;
  onOpenFile?: (path: string) => void;
  variant?: "tool" | "composer";
  inboxPendingCount?: number;
  workHookAlert?: {
    readonly event: string;
    readonly body: string;
    readonly blocked: boolean;
  } | null;
  onDismissWorkHookAlert?: () => void;
  /** Parent-provided runtime — skips local `/runtime` fetch when defined. */
  runtimeSnapshot?: RuntimeSnapshot | null;
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
  onOpenDiff,
  onOpenFiles,
  onOpenFile,
  variant = "tool",
  inboxPendingCount = 0,
  workHookAlert = null,
  onDismissWorkHookAlert,
  runtimeSnapshot,
}: Props) {
  const hasPlan = Boolean(planMd.trim());
  const isComposer = variant === "composer";
  const disabled = running || synthesizing || runBusy;
  const showPlanStalePanel = Boolean(planStaleNotice);
  const showSyncFailedBar =
    Boolean(planMeta.pendingAgreement) && !showPlanStalePanel;
  const ownsRuntimeFetch = runtimeSnapshot === undefined;
  const { runtime: fetchedRuntime } = useSessionRuntime(sessionId, {
    run: session?.run,
    enabled: ownsRuntimeFetch,
  });
  const runtime = ownsRuntimeFetch ? fetchedRuntime : runtimeSnapshot;
  const executions = useMemo(
    () => (session?.run?.executions as PlanExecutionRecord[] | undefined) ?? [],
    [session?.run],
  );
  const latestExecution = executions.length
    ? executions[executions.length - 1]
    : null;
  const gjcPhase = resolveGjcPipelinePhase({
    planWorkflow,
    runtime,
    latestExecution,
    hasPlan,
  });
  const gjcMeta = gjcPipelineMetaLine(gjcPhase, planWorkflow?.notice);
  const externalRunnerEnabled = Boolean(runtime?.external?.runner_enabled);
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
        onOpenFiles?.();
        return;
      }
      const id = workDecisionActionElementId(actionId);
      document.getElementById(id)?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    },
    [onOpenFiles],
  );

  const workflowPhase = (
    planWorkflow?.phase ??
    runtime?.plan_workflow?.phase ??
    ""
  ).toUpperCase();
  const showClarifyWork =
    (workflowPhase === "CLARIFY" || workflowPhase === "INTAKE") &&
    hasPlanWorkflowClarifySurface({
      phase: workflowPhase,
      inboxPendingCount,
      notice:
        planWorkflow?.notice ?? runtime?.plan_workflow?.notice ?? undefined,
    });

  if (showClarifyWork && !hasPlan && !planApproval?.enabled) {
    if (isComposer) return null;
    return (
      <div className="work-surface tools-work-empty">
        <div className="empty-state">
          <span className="empty-state__title">
            {inboxPendingCount > 0 ? "Clarify 질문 대기" : "Clarify 진행 중"}
          </span>
          <span className="empty-state__hint">
            {inboxPendingCount > 0
              ? "Composer Human Inbox에서 에이전트 질문에 답하세요."
              : "에이전트가 Inbox에 질문을 올릴 때까지 기다리세요."}
          </span>
        </div>
      </div>
    );
  }

  if (!hasPlan) {
    if (isComposer) return null;
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
        {!isComposer ? (
          <div className="work-surface work-surface--chrome work-chrome">
            <GjcPipelineBar
              phase={gjcPhase}
              metaLine={gjcMeta}
              externalRunnerEnabled={externalRunnerEnabled}
            />
            <WorkStatusBar
              phase={workPhase}
              metaLine={workPlanMetaLine(planMeta)}
              hasPlan={hasPlan}
            />
            <GjcExternalHandoffStrip execution={latestExecution} />
          </div>
        ) : null}
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
      {variant === "tool" ? (
        <div className="work-surface work-surface--chrome work-chrome">
          <GjcPipelineBar
            phase={gjcPhase}
            metaLine={gjcMeta}
            externalRunnerEnabled={externalRunnerEnabled}
          />
          <WorkStatusBar
            phase={workPhase}
            metaLine={workPlanMetaLine(planMeta)}
            hasPlan={hasPlan}
          />
          <GjcExternalHandoffStrip execution={latestExecution} />
          <WorkDecisionPanel
            summary={decisionSummary}
            onAction={handleDecisionAction}
          />
        </div>
      ) : null}

      {showPlanStalePanel ? (
        <div className="work-surface work-surface--alert work-plan-stale">
          <p className="plan-stale">{planStaleNotice}</p>
        </div>
      ) : null}

      {showSyncFailedBar && !isComposer ? (
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
          {!isComposer ? (
            <p className="plan-card__muted">
              Plan 승인은 유지되었습니다. 아래 Dry-run으로 다시 실행할 수
              있습니다.
            </p>
          ) : null}
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
        onOpenDiff={onOpenDiff}
        onOpenFiles={onOpenFiles}
        onOpenFile={onOpenFile}
        sessionIdForObjections={sessionId}
        onObjectionResolved={onSessionUpdated}
        variant={variant}
        planFileLabel={
          typeof session?.run?.active_plan_relpath === "string"
            ? session.run.active_plan_relpath
            : "plan.md"
        }
      />
    </div>
  );
}
