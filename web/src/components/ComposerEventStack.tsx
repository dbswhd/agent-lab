import { useEffect, useMemo, useRef } from "react";
import type {
  PlanExecutionRecord,
  PlanWorkflowRecord,
  SessionDetail,
} from "../api/client";
import type { RoomTasksPayload } from "../api/client";
import type { PlanMetaView } from "../utils/planMeta";
import type { StoredPlanAction } from "../utils/planExecuteHistory";
import type { ConsensusDryRunProposal } from "./ConsensusDryRunGateBar";
import { WorkToolPanel, type WorkFocusTarget } from "./WorkToolPanel";
import { HumanInboxPanel } from "./HumanInboxPanel";
import { ExecuteQueueBar } from "./ExecuteQueueBar";
import { ConsensusDryRunGateBar } from "./ConsensusDryRunGateBar";
import { WorkPhaseChip } from "./WorkPhaseChip";
import {
  WorkPlanApprovalSection,
  type PlanApprovalHost,
} from "./WorkPlanApprovalSection";
import { WorkClarifyPanel } from "./WorkClarifyPanel";
import { fetchSessionRuntime, type RuntimeSnapshot } from "../api/client";
import { useState } from "react";
import { resolveWorkPhase } from "../utils/workStatusPhase";
import { workPlanMetaLine } from "../utils/planMeta";
import { hasPlanWorkflowClarifySurface } from "../utils/planWorkflowView";
import {
  COMPOSER_STACK_FOCUS_EVENT,
  type ComposerStackFocus,
} from "../utils/composerStackFocus";
import { workFocusElementId } from "../utils/workFocusTargets";

type Props = {
  readonly sessionId: string;
  readonly session: SessionDetail | null;
  readonly planMd: string;
  readonly planMeta: PlanMetaView;
  readonly planStaleNotice?: string | null;
  readonly workFocus?: WorkFocusTarget | null;
  readonly onWorkFocusHandled?: () => void;
  readonly synthesizing: boolean;
  readonly running: boolean;
  readonly runBusy: boolean;
  readonly executeBusy: boolean;
  readonly onSynthesizeNow: () => void;
  readonly onPlanRefClick: (line: number) => void;
  readonly onFocusTask: (taskId: string) => void;
  readonly onFocusObjection: (id: string, actionIndex?: number) => void;
  readonly onSessionUpdated: () => void;
  readonly roomTasks: RoomTasksPayload | null;
  readonly cursorReady: boolean;
  readonly executeError?: string | null;
  readonly planWorkflow?: PlanWorkflowRecord;
  readonly planApproval?: PlanApprovalHost | null;
  readonly workHookAlert?: {
    readonly event: string;
    readonly body: string;
    readonly blocked: boolean;
  } | null;
  readonly onDismissWorkHookAlert?: () => void;
  readonly inboxPendingCount: number;
  readonly inboxReloadKey: number;
  readonly currentPlanRevision: string | null;
  readonly onInboxResolved: () => void;
  readonly onInboxBuildStarted: () => void;
  readonly onInboxRefClick: (ref: string) => void;
  readonly execPending: PlanExecutionRecord | null;
  readonly storedActions: StoredPlanAction[];
  readonly onExecuteApprove: () => void;
  readonly onExecuteReject: () => void;
  readonly showExecuteQueue: boolean;
  readonly consensusProposal: ConsensusDryRunProposal | null;
  readonly showConsensusGate: boolean;
  readonly consensusGateBusy: boolean;
  readonly onConsensusDryRun: () => void;
  readonly onConsensusDismiss: () => void;
  readonly onOpenDiff: () => void;
  readonly onOpenFiles: () => void;
  readonly disabled: boolean;
};

/** Human action SSOT above the composer — inbox, plan approval, execute, consensus. */
export function ComposerEventStack({
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
  executeBusy,
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
  workHookAlert = null,
  onDismissWorkHookAlert,
  inboxPendingCount,
  inboxReloadKey,
  currentPlanRevision,
  onInboxResolved,
  onInboxBuildStarted,
  onInboxRefClick,
  execPending,
  storedActions,
  onExecuteApprove,
  onExecuteReject,
  showExecuteQueue,
  consensusProposal,
  showConsensusGate,
  consensusGateBusy,
  onConsensusDryRun,
  onConsensusDismiss,
  onOpenDiff,
  onOpenFiles,
  disabled,
}: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const hasPlan = Boolean(planMd.trim());
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
    function onFocus(event: Event) {
      const focus = (event as CustomEvent<ComposerStackFocus | undefined>)
        .detail;
      rootRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      if (!focus || focus === "inbox" || focus === "activity") return;
      window.setTimeout(() => {
        document
          .getElementById(workFocusElementId(focus))
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
        onWorkFocusHandled?.();
      }, 80);
    }
    window.addEventListener(COMPOSER_STACK_FOCUS_EVENT, onFocus);
    return () =>
      window.removeEventListener(COMPOSER_STACK_FOCUS_EVENT, onFocus);
  }, [onWorkFocusHandled]);

  useEffect(() => {
    if (!workFocus) return;
    rootRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    window.setTimeout(() => {
      document
        .getElementById(workFocusElementId(workFocus))
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
      onWorkFocusHandled?.();
    }, 80);
  }, [workFocus, onWorkFocusHandled]);

  const workflowPhase = (
    planWorkflow?.phase ??
    runtime?.plan_workflow?.phase ??
    ""
  ).toUpperCase();

  const showClarifyWork = useMemo(
    () =>
      (workflowPhase === "CLARIFY" || workflowPhase === "INTAKE") &&
      hasPlanWorkflowClarifySurface({
        phase: workflowPhase,
        inboxPendingCount,
        notice:
          planWorkflow?.notice ?? runtime?.plan_workflow?.notice ?? undefined,
        clarifierInterview: runtime?.clarifier_interview ?? null,
      }),
    [
      inboxPendingCount,
      planWorkflow?.notice,
      runtime?.clarifier_interview,
      runtime?.plan_workflow?.notice,
      workflowPhase,
    ],
  );

  const workPhase = useMemo(() => {
    const executions =
      (session?.run?.executions as PlanExecutionRecord[] | undefined) ?? [];
    const latestExecution = executions.length
      ? executions[executions.length - 1]
      : null;
    return (
      runtime?.work_phase ??
      resolveWorkPhase({
        hasPlan,
        hasPendingExecution: Boolean(runtime?.execute.has_pending),
        hasDryRunDiff: Boolean(runtime?.execute.has_dry_run_diff),
        pendingAgreement: Boolean(planMeta.pendingAgreement),
        latestExecution,
      })
    );
  }, [hasPlan, planMeta.pendingAgreement, runtime, session?.run?.executions]);

  const showWorkSurface =
    (planWorkflow?.enabled
      ? workflowPhase === "APPROVED" && hasPlan
      : hasPlan) ||
    showClarifyWork ||
    Boolean(execPending);

  return (
    <div className="composer-event-stack" ref={rootRef}>
      {inboxPendingCount > 0 ? (
        <div className="composer-event-stack__section composer-question-surface">
          <HumanInboxPanel
            sessionId={sessionId}
            reloadKey={inboxReloadKey}
            planRevision={currentPlanRevision}
            onResolved={onInboxResolved}
            onBuildStarted={onInboxBuildStarted}
            disabled={disabled}
            presentation="composer"
            onRefClick={onInboxRefClick}
          />
        </div>
      ) : null}

      {showClarifyWork && !hasPlan && !planApproval?.enabled ? (
        <div className="composer-event-stack__section">
          <WorkClarifyPanel
            planWorkflow={planWorkflow}
            runtime={runtime}
            inboxPendingCount={inboxPendingCount}
          />
        </div>
      ) : null}

      {planApproval?.enabled ? (
        <div className="composer-event-stack__section">
          <WorkPlanApprovalSection
            planMd={planMd}
            approval={planApproval}
            objections={roomTasks?.open_objections ?? []}
            blockedReason={
              planStaleNotice ??
              (planMeta.pendingAgreement ? planMeta.freshnessLabel : null)
            }
            onFocusObjection={onFocusObjection}
            sessionId={sessionId}
            onObjectionResolved={onSessionUpdated}
            variant="strip"
            onOpenFiles={onOpenFiles}
            planFileLabel={
              typeof session?.run?.active_plan_relpath === "string"
                ? session.run.active_plan_relpath
                : "plan.md"
            }
          />
        </div>
      ) : null}

      {showExecuteQueue && execPending ? (
        <div className="composer-event-stack__section workspace-event-strip workspace-event-strip--review">
          <ExecuteQueueBar
            pending={execPending}
            storedActions={storedActions}
            busy={executeBusy}
            disabled={disabled}
            compact
            onApprove={onExecuteApprove}
            onReject={onExecuteReject}
            onOpenPlan={onOpenDiff}
          />
        </div>
      ) : null}

      {showConsensusGate && consensusProposal ? (
        <div className="composer-event-stack__section workspace-event-strip workspace-event-strip--review">
          <ConsensusDryRunGateBar
            proposal={consensusProposal}
            busy={consensusGateBusy || executeBusy}
            disabled={disabled}
            onDryRun={onConsensusDryRun}
            onOpenPlan={onOpenDiff}
            onDismiss={onConsensusDismiss}
          />
        </div>
      ) : null}

      {showWorkSurface && !planApproval?.enabled ? (
        <div className="composer-event-stack__section composer-event-stack__work">
          <WorkToolPanel
            sessionId={sessionId}
            session={session}
            planMd={planMd}
            planMeta={planMeta}
            planStaleNotice={planStaleNotice}
            workFocus={workFocus}
            onWorkFocusHandled={onWorkFocusHandled}
            synthesizing={synthesizing}
            running={running}
            runBusy={runBusy}
            onSynthesizeNow={onSynthesizeNow}
            onPlanRefClick={onPlanRefClick}
            onFocusTask={onFocusTask}
            onFocusObjection={onFocusObjection}
            onSessionUpdated={onSessionUpdated}
            roomTasks={roomTasks}
            cursorReady={cursorReady}
            executeError={executeError}
            planWorkflow={planWorkflow}
            planApproval={null}
            inboxPendingCount={inboxPendingCount}
            workHookAlert={workHookAlert}
            onDismissWorkHookAlert={onDismissWorkHookAlert}
            onOpenDiff={onOpenDiff}
            onOpenFiles={onOpenFiles}
            variant="composer"
          />
        </div>
      ) : null}

      {hasPlan && (!planWorkflow?.enabled || workflowPhase === "APPROVED") ? (
        <WorkPhaseChip
          phase={workPhase}
          metaLine={workPlanMetaLine(planMeta)}
        />
      ) : null}
    </div>
  );
}
