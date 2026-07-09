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
import { ComposerStrip } from "./ComposerStrip";
import { WorkPhaseChip } from "./WorkPhaseChip";
import {
  WorkPlanApprovalSection,
  type PlanApprovalHost,
} from "./WorkPlanApprovalSection";
import { fetchSessionRuntime, type RuntimeSnapshot } from "../api/client";
import { useState } from "react";
import { resolveWorkPhase } from "../utils/workStatusPhase";
import { workPlanMetaLine } from "../utils/planMeta";
import {
  hasPlanWorkflowClarifyNotice,
  hasPlanWorkflowClarifySurface,
  planWorkflowNoticeLabel,
} from "../utils/planWorkflowView";
import {
  COMPOSER_STACK_FOCUS_EVENT,
  type ComposerStackFocus,
} from "../utils/composerStackFocus";
import { workFocusElementId } from "../utils/workFocusTargets";
import {
  pendingComposerStackLanes,
  resolveActiveComposerStackLane,
} from "../utils/composerStackLane";
import { useLocale } from "../i18n/useLocale";

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
  readonly onOpenFile: (path: string) => void;
  readonly disabled: boolean;
};

const LANE_LABEL_KO: Record<string, string> = {
  plan_approval: "Plan 승인",
  clarify: "명료화",
  execute_queue: "실행 승인",
  consensus: "합의 dry-run",
  work: "할 일",
};

const LANE_LABEL_EN: Record<string, string> = {
  plan_approval: "Plan approval",
  clarify: "Clarify",
  execute_queue: "Execute approval",
  consensus: "Consensus dry-run",
  work: "To-dos",
};

/** Human action SSOT above the composer — one lane at a time by precedence. */
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
  onOpenFile,
  disabled,
}: Props) {
  const { locale, msg } = useLocale();
  const ko = locale === "ko";
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

  const workflowNotice =
    planWorkflow?.notice ?? runtime?.plan_workflow?.notice ?? undefined;

  const showClarifyWork = useMemo(
    () =>
      (workflowPhase === "CLARIFY" || workflowPhase === "INTAKE") &&
      hasPlanWorkflowClarifySurface({
        phase: workflowPhase,
        inboxPendingCount,
        notice: workflowNotice,
      }),
    [inboxPendingCount, workflowNotice, workflowPhase],
  );

  const showClarifyNotice = useMemo(
    () =>
      hasPlanWorkflowClarifyNotice({
        phase: workflowPhase,
        notice: workflowNotice,
      }),
    [workflowNotice, workflowPhase],
  );

  const clarifyNoticeLabel = planWorkflowNoticeLabel(workflowNotice, msg);
  const clarifyStripTitle = ko ? "명료화 필요" : "Clarification needed";
  const clarifyStripDescription =
    workflowPhase === "INTAKE"
      ? ko
        ? "계획을 이어가기 전에 입력을 더 분명히 해야 합니다."
        : "The workflow needs clearer input before it can continue."
      : ko
        ? "계획을 진행하기 전에 누락된 정보를 정리하는 단계입니다."
        : "The workflow is collecting missing context before continuing.";

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

  const laneInput = useMemo(
    () => ({
      inboxPendingCount,
      planApprovalEnabled: Boolean(planApproval?.enabled),
      showClarifyNotice,
      hasPlan,
      showExecuteQueue,
      execPending: Boolean(execPending),
      showConsensusGate,
      consensusProposal,
      showWorkSurface,
    }),
    [
      consensusProposal,
      execPending,
      hasPlan,
      inboxPendingCount,
      planApproval?.enabled,
      showClarifyNotice,
      showConsensusGate,
      showExecuteQueue,
      showWorkSurface,
    ],
  );

  const pendingLanes = useMemo(
    () => pendingComposerStackLanes(laneInput),
    [laneInput],
  );
  const activeLane = useMemo(
    () => resolveActiveComposerStackLane(laneInput),
    [laneInput],
  );
  const queuedLanes = pendingLanes.slice(1);

  if (!activeLane) {
    return null;
  }

  const planFileLabel =
    typeof session?.run?.active_plan_relpath === "string"
      ? session.run.active_plan_relpath
      : "plan.md";

  return (
    <div className="composer-stack-scroll" ref={rootRef}>
      <div className="composer-event-stack" data-composer-lane={activeLane}>
        {activeLane === "inbox" ? (
          <div className="composer-event-stack__section composer-question-surface">
            <HumanInboxPanel
              sessionId={sessionId}
              reloadKey={inboxReloadKey}
              planRevision={currentPlanRevision}
              onResolved={onInboxResolved}
              onBuildStarted={onInboxBuildStarted}
              disabled={false}
              onRefClick={onInboxRefClick}
            />
          </div>
        ) : null}

        {activeLane === "clarify" && clarifyNoticeLabel ? (
          <div className="composer-event-stack__section workspace-event-strip">
            <ComposerStrip
              tone="warn"
              role="status"
              ariaLabel={ko ? "명료화 상태" : "Clarification status"}
              badge={ko ? "Clarify" : "Clarify"}
              title={clarifyStripTitle}
              description={clarifyStripDescription}
              items={[clarifyNoticeLabel]}
              compact
            />
          </div>
        ) : null}

        {activeLane === "plan_approval" && planApproval?.enabled ? (
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
              planFileLabel={planFileLabel}
            />
          </div>
        ) : null}

        {activeLane === "execute_queue" && execPending ? (
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

        {activeLane === "consensus" && consensusProposal ? (
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

        {activeLane === "work" ? (
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
              onOpenFile={onOpenFile}
              variant="composer"
            />
            {hasPlan &&
            (!planWorkflow?.enabled || workflowPhase === "APPROVED") ? (
              <WorkPhaseChip
                phase={workPhase}
                metaLine={workPlanMetaLine(planMeta)}
              />
            ) : null}
          </div>
        ) : null}

        {queuedLanes.length > 0 ? (
          <p className="composer-stack-queue-hint" role="status">
            {ko
              ? `다음: ${queuedLanes
                  .map((lane) => LANE_LABEL_KO[lane] ?? lane)
                  .join(" → ")}`
              : `Next: ${queuedLanes
                  .map((lane) => LANE_LABEL_EN[lane] ?? lane)
                  .join(" → ")}`}
          </p>
        ) : null}
      </div>
    </div>
  );
}
