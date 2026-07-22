import { useEffect, useMemo, useRef } from "react";
import type {
  PlanExecutionRecord,
  PlanWorkflowRecord,
  RuntimeSnapshot,
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
import { useSessionRuntime } from "../hooks/useSessionRuntime";
import { resolveWorkPhase } from "../utils/workStatusPhase";
import { workPlanMetaLine } from "../utils/planMeta";
import { workPhaseMetaLine } from "../utils/orchestrationDrift";
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
import { resolveComposerStackSnapshot } from "../utils/composerStackLane";
import { useLocale } from "../i18n/useLocale";
import { DecisionQueueHeader } from "./DecisionQueueHeader";
import { useMissionReadModel } from "../utils/missionReadModel";

function clarifyStripDescriptionText(
  ko: boolean,
  workflowPhase: string,
): string {
  if (ko) {
    return workflowPhase === "INTAKE"
      ? "계획을 이어가기 전에 입력을 더 분명히 해야 합니다."
      : "계획을 진행하기 전에 누락된 정보를 정리하는 단계입니다.";
  }
  return workflowPhase === "INTAKE"
    ? "The workflow needs clearer input before it can continue."
    : "The workflow is collecting missing context before continuing.";
}

function isRuntimeWorkPhase(
  value: string | null | undefined,
): value is RuntimeSnapshot["work_phase"] {
  return (
    value === "plan_draft" ||
    value === "review_needed" ||
    value === "execute_pending" ||
    value === "merge_verify" ||
    value === "done"
  );
}

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
  readonly onRetryExecute?: () => void;
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
  readonly onExecuteReverify?: (executionId: string) => void;
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
  onRetryExecute,
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
  onExecuteReverify,
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
  const { runtime } = useSessionRuntime(sessionId, { run: session?.run });
  const { model: missionReadModel } = useMissionReadModel(
    sessionId,
    inboxReloadKey,
  );
  const effectiveInboxPendingCount =
    missionReadModel?.inbox_summary?.pending_count ?? inboxPendingCount;

  function scrollStackRoot() {
    rootRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function scrollWorkFocusTarget(
    target: ComposerStackFocus | WorkFocusTarget | null | undefined,
  ) {
    if (!target || target === "inbox" || target === "activity") return;
    window.setTimeout(() => {
      document
        .getElementById(workFocusElementId(target))
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
      onWorkFocusHandled?.();
    }, 80);
  }

  useEffect(() => {
    function onFocus(event: Event) {
      const focus = (event as CustomEvent<ComposerStackFocus | undefined>)
        .detail;
      scrollStackRoot();
      scrollWorkFocusTarget(focus);
    }
    window.addEventListener(COMPOSER_STACK_FOCUS_EVENT, onFocus);
    return () =>
      window.removeEventListener(COMPOSER_STACK_FOCUS_EVENT, onFocus);
  }, [onWorkFocusHandled]);

  useEffect(() => {
    if (!workFocus) return;
    scrollStackRoot();
    scrollWorkFocusTarget(workFocus);
  }, [workFocus, onWorkFocusHandled]);

  const workflowPhase = (
    missionReadModel?.plan?.phase ??
    planWorkflow?.phase ??
    runtime?.plan_workflow?.phase ??
    ""
  ).toUpperCase();

  const workflowNotice =
    planWorkflow?.notice ?? runtime?.plan_workflow?.notice ?? undefined;

  const showClarifyWork =
    (workflowPhase === "CLARIFY" || workflowPhase === "INTAKE") &&
    hasPlanWorkflowClarifySurface({
      phase: workflowPhase,
      inboxPendingCount: effectiveInboxPendingCount,
      notice: workflowNotice,
    });

  const showClarifyNotice = hasPlanWorkflowClarifyNotice({
    phase: workflowPhase,
    notice: workflowNotice,
  });

  const clarifyNoticeLabel = planWorkflowNoticeLabel(workflowNotice, msg);
  const clarifyStripTitle = ko ? "명료화 필요" : "Clarification needed";
  const clarifyStripDescription = clarifyStripDescriptionText(
    ko,
    workflowPhase,
  );

  const workPhase = useMemo(() => {
    const executions =
      (session?.run?.executions as PlanExecutionRecord[] | undefined) ?? [];
    const latestExecution = executions.length
      ? executions[executions.length - 1]
      : null;
    return (
      (isRuntimeWorkPhase(missionReadModel?.work_phase)
        ? missionReadModel.work_phase
        : null) ??
      runtime?.work_phase ??
      resolveWorkPhase({
        hasPlan,
        hasPendingExecution: Boolean(runtime?.execute?.has_pending),
        hasDryRunDiff: Boolean(runtime?.execute?.has_dry_run_diff),
        pendingAgreement: Boolean(planMeta.pendingAgreement),
        latestExecution,
      })
    );
  }, [
    hasPlan,
    missionReadModel?.work_phase,
    planMeta.pendingAgreement,
    runtime,
    session?.run?.executions,
  ]);

  const showWorkSurface =
    (planWorkflow?.enabled
      ? workflowPhase === "APPROVED" && hasPlan
      : hasPlan) ||
    showClarifyWork ||
    Boolean(execPending);

  const { activeLane, queuedLanes, pendingDecisionCount } = useMemo(
    () =>
      resolveComposerStackSnapshot({
        inboxPendingCount: effectiveInboxPendingCount,
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
      effectiveInboxPendingCount,
      planApproval?.enabled,
      showClarifyNotice,
      showConsensusGate,
      showExecuteQueue,
      showWorkSurface,
    ],
  );

  // Room discuss/plan rounds converge in chat with no chat-native nudge toward
  // the execute gate — mission_loop.enabled stays false and nothing else in
  // this stack ever blocks, so the composer silently renders nothing. Point
  // at /execute explicitly rather than leave the human to discover
  // mission-loop's REST API or the header Autonomy dial on their own.
  // Covers both: activeLane is null (nothing else pending — the common case,
  // since plan_workflow separately gates "work" behind its own APPROVED
  // phase) and activeLane === "work" (plan_workflow already APPROVED).
  const missionLoop = session?.run?.mission_loop as
    | { enabled?: boolean; phase?: string }
    | undefined;
  const showExecuteHint =
    (!activeLane || activeLane === "work") &&
    hasPlan &&
    missionLoop?.phase === "DISCUSS" &&
    missionLoop?.enabled !== true;

  // Consensus vs analyze-only is invisible from the transcript — both look like
  // "a round ran," but only one flows into record_consensus_agreement / plan.md
  // auto-sync. Surface the just-completed turn's actual path so the human isn't
  // left guessing why plan.md didn't update after what looked like a normal round.
  const lastTurn = useMemo(() => {
    const turns = session?.run?.turns as
      | Array<{ consensus_mode?: boolean; consensus?: unknown }>
      | undefined;
    return turns && turns.length > 0 ? turns[turns.length - 1] : null;
  }, [session?.run?.turns]);
  const lastTurnReachedConsensus =
    lastTurn != null &&
    typeof lastTurn.consensus === "object" &&
    lastTurn.consensus !== null;
  const showTurnModeBadge =
    !activeLane && !running && !showExecuteHint && lastTurn != null;

  if (!activeLane) {
    if (showExecuteHint) {
      return (
        <div className="composer-stack-scroll" ref={rootRef}>
          <div
            className="composer-event-stack"
            data-composer-lane="execute_hint"
          >
            <div className="composer-event-stack__section workspace-event-strip">
              <ComposerStrip
                tone="accent"
                role="status"
                ariaLabel={ko ? "실행 안내" : "Execute hint"}
                badge="Execute"
                title={ko ? "합의가 끝났나요?" : "Converged?"}
                description={
                  ko
                    ? "`/execute`를 입력하면 현재 plan.md를 worktree dry-run + Oracle 검증으로 보냅니다."
                    : "Type `/execute` to send the current plan.md to worktree dry-run + Oracle verify."
                }
                compact
              />
            </div>
          </div>
        </div>
      );
    }
    if (!showTurnModeBadge) return null;
    return (
      <div className="composer-stack-scroll" ref={rootRef}>
        <div
          className="composer-event-stack"
          data-composer-lane="turn_mode_hint"
        >
          <div className="composer-event-stack__section workspace-event-strip">
            <ComposerStrip
              tone="neutral"
              role="status"
              ariaLabel={ko ? "턴 유형" : "Turn type"}
              badge={
                lastTurnReachedConsensus
                  ? ko
                    ? "합의"
                    : "Consensus"
                  : ko
                    ? "분석 전용"
                    : "Analyze-only"
              }
              title={
                lastTurnReachedConsensus
                  ? ko
                    ? "합의 라운드가 기록됐습니다"
                    : "Consensus round recorded"
                  : ko
                    ? "이번 턴은 분석 전용입니다"
                    : "This turn was analyze-only"
              }
              description={
                lastTurnReachedConsensus
                  ? ko
                    ? "plan.md 자동 동기화 대상입니다."
                    : "Eligible for plan.md auto-sync."
                  : ko
                    ? "합의 기록 없음 — plan.md가 자동으로 갱신되지 않습니다."
                    : "No consensus recorded — plan.md will not auto-sync."
              }
              compact
            />
          </div>
        </div>
      </div>
    );
  }

  const planFileLabel =
    typeof session?.run?.active_plan_relpath === "string"
      ? session.run.active_plan_relpath
      : "plan.md";

  return (
    <div className="composer-stack-scroll" ref={rootRef}>
      <div className="composer-event-stack" data-composer-lane={activeLane}>
        {activeLane !== "work" ? (
          <DecisionQueueHeader
            activeLane={activeLane}
            queuedLanes={queuedLanes}
            pendingCount={pendingDecisionCount}
            locale={locale}
          />
        ) : null}
        {showExecuteHint ? (
          <div className="composer-event-stack__section workspace-event-strip">
            <ComposerStrip
              tone="accent"
              role="status"
              ariaLabel={ko ? "실행 안내" : "Execute hint"}
              badge="Execute"
              title={ko ? "합의가 끝났나요?" : "Converged?"}
              description={
                ko
                  ? "`/execute`를 입력하면 현재 plan.md를 worktree dry-run + Oracle 검증으로 보냅니다."
                  : "Type `/execute` to send the current plan.md to worktree dry-run + Oracle verify."
              }
              compact
            />
          </div>
        ) : null}
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
              onReverify={onExecuteReverify}
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
              onRetryExecute={onRetryExecute}
              planWorkflow={planWorkflow}
              planApproval={null}
              inboxPendingCount={inboxPendingCount}
              workHookAlert={workHookAlert}
              onDismissWorkHookAlert={onDismissWorkHookAlert}
              onOpenDiff={onOpenDiff}
              onOpenFiles={onOpenFiles}
              onOpenFile={onOpenFile}
              variant="composer"
              runtimeSnapshot={runtime}
            />
            {hasPlan &&
            (!planWorkflow?.enabled || workflowPhase === "APPROVED") ? (
              <WorkPhaseChip
                phase={workPhase}
                metaLine={workPhaseMetaLine(
                  runtime?.orchestration,
                  workPlanMetaLine(planMeta),
                )}
              />
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
