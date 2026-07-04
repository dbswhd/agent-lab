import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import type {
  PlanWorkflowRecord,
  RoomObjection,
  RoomTasksPayload,
  SessionDetail,
} from "../api/client";
import type { ConsensusDryRunProposal } from "../components/ConsensusDryRunGateBar";
import type { Locale } from "../i18n/locale";
import type { usePlanExecute } from "./usePlanExecute";
import { executionApprovalGate } from "../utils/executeApprovalGate";
import { dispatchNotification } from "../utils/pushNotification";
import { notifyDesktop } from "../utils/desktopNotify";
import { isPlanWorkflowAwaitingApproval } from "../utils/planComposerSync";
import { CUSTOM_WORKSPACE_ID } from "../utils/sessionSetup";
import {
  isPlanWorkflowComposerHint,
  isPlanWorkflowPhaseBanner,
} from "../utils/planWorkflowView";
import {
  DEMO_CONSENSUS_PROPOSAL,
  DEMO_EXEC_PENDING,
  DEMO_EXEC_PENDING_BLOCKED,
  DEMO_OBJECTION_NOTICE,
} from "../utils/tweaksDemoFixtures";
import type { AgentHealthRow } from "../api/client";

type PlanExecuteShellSlice = Pick<
  ReturnType<typeof usePlanExecute>,
  | "activePending"
  | "pendingTitle"
  | "openObjectionBlock"
  | "busy"
  | "executions"
  | "error"
>;

export type PlanShellTweaks = {
  execQueueDemo: false | "hidden" | "normal" | "blocked";
  consensusGateDemo: boolean;
  objectionDemo: boolean;
};

export type UseRoomPlanShellStateOptions = {
  sessionId: string | null;
  sessionRun: SessionDetail["run"] | undefined;
  planMd: string;
  roomTasks: RoomTasksPayload | null;
  planExecute: PlanExecuteShellSlice;
  consensusProposal: ConsensusDryRunProposal | null;
  verifiedLoopPendingApproval: boolean;
  tweaks: PlanShellTweaks;
  running: boolean;
  runBusy: boolean;
  synthesizing: boolean;
  loading?: boolean;
  waitingForSession: boolean;
  isNew: boolean;
  selected: string[];
  healthAgents: AgentHealthRow[];
  text: string;
  pendingFiles: { id: string }[];
  workspaceId: string;
  workspacePath: string | null;
  locale: Locale;
  localeMsg: { planWorkflowComposerBlocked: string; composerPlaceholder: string };
  pushMacNotification: (payload: { title: string; body?: string }) => void;
  /** Ref wired after workbench tabs — opens plan file on HUMAN_PENDING. */
  openPlanApprovalWorkbenchRef?: MutableRefObject<((relpath: string) => void) | null>;
};

/** Plan workflow banners, execute queue strip, composer gate flags (F9 slice 4b). */
export function useRoomPlanShellState({
  sessionId,
  sessionRun,
  planMd,
  roomTasks,
  planExecute,
  consensusProposal,
  verifiedLoopPendingApproval,
  tweaks,
  running,
  runBusy,
  synthesizing,
  loading,
  waitingForSession,
  isNew,
  selected,
  healthAgents,
  text,
  pendingFiles,
  workspaceId,
  workspacePath,
  locale,
  localeMsg,
  pushMacNotification,
  openPlanApprovalWorkbenchRef,
}: UseRoomPlanShellStateOptions) {
  const [hideApprovedPlanBanner, setHideApprovedPlanBanner] = useState(false);
  const prevExecPendingIdRef = useRef<string | null>(null);

  const hasPendingExecution = Boolean(planExecute.activePending);
  const hasDryRunDiff =
    consensusProposal != null || Boolean(planExecute.activePending?.diff);
  const hasBlocker = Boolean(
    roomTasks &&
    ((roomTasks.consensus_task_blockers ?? []).length > 0 ||
      roomTasks.consensus_tasks_ready === false ||
      (roomTasks.open_objection_count ?? 0) > 0),
  );
  const consensusBlocked = Boolean(
    roomTasks &&
    ((roomTasks.consensus_task_blockers ?? []).length > 0 ||
      roomTasks.consensus_tasks_ready === false),
  );

  const showExecuteQueueStrip =
    tweaks.execQueueDemo === "hidden"
      ? false
      : tweaks.execQueueDemo === "normal" || tweaks.execQueueDemo === "blocked"
        ? true
        : Boolean(sessionId) && hasPendingExecution;
  const demoExecPending =
    tweaks.execQueueDemo === "blocked"
      ? DEMO_EXEC_PENDING_BLOCKED
      : tweaks.execQueueDemo === "normal"
        ? DEMO_EXEC_PENDING
        : null;
  const execPendingForBar = demoExecPending ?? planExecute.activePending;
  const consensusForBar = tweaks.consensusGateDemo
    ? DEMO_CONSENSUS_PROPOSAL
    : consensusProposal;

  useEffect(() => {
    const pending = planExecute.activePending;
    if (!sessionId || !pending?.id) {
      prevExecPendingIdRef.current = null;
      return;
    }
    if (prevExecPendingIdRef.current === pending.id) return;
    prevExecPendingIdRef.current = pending.id;
    const gate = executionApprovalGate(pending);
    dispatchNotification(
      {
        tier: "P1",
        title: gate.blocked ? "Execute 차단" : "Execute 승인 필요",
        body: gate.reason ?? planExecute.pendingTitle ?? undefined,
        sessionId,
        kind: gate.blocked ? "execute_blocked" : "execute_pending",
        entityId: pending.id,
        toastAction: { type: "composer", focus: "execute" },
      },
      pushMacNotification,
      notifyDesktop,
    );
  }, [
    sessionId,
    planExecute.activePending?.id,
    planExecute.pendingTitle,
    pushMacNotification,
  ]);

  const showConsensusDryRunGate =
    !showExecuteQueueStrip &&
    (tweaks.consensusGateDemo ||
      (Boolean(sessionId) && consensusProposal != null));

  const planWorkflow = sessionRun?.plan_workflow as PlanWorkflowRecord | undefined;
  const planWorkflowPlanIntent =
    typeof sessionRun?.plan_intent === "string" ? sessionRun.plan_intent : null;
  const planWorkflowActive = Boolean(planWorkflow?.enabled);
  const showPlanApproval =
    planWorkflowActive &&
    (planWorkflow?.phase === "HUMAN_PENDING" || verifiedLoopPendingApproval);

  const showPlanWorkflowBanner =
    planWorkflowActive &&
    !showPlanApproval &&
    isPlanWorkflowPhaseBanner(planWorkflow?.phase);

  const showPlanWorkflowComposerHint =
    planWorkflowActive &&
    isPlanWorkflowComposerHint(planWorkflow?.phase) &&
    !(planWorkflow?.phase === "APPROVED" && hideApprovedPlanBanner) &&
    !running &&
    !runBusy &&
    !synthesizing;

  useEffect(() => {
    if (planWorkflow?.phase !== "APPROVED") {
      setHideApprovedPlanBanner(false);
      return;
    }
    setHideApprovedPlanBanner(false);
    const timer = window.setTimeout(
      () => setHideApprovedPlanBanner(true),
      8000,
    );
    return () => window.clearTimeout(timer);
  }, [sessionId, planWorkflow?.phase]);

  const activePlanRelpath =
    typeof sessionRun?.active_plan_relpath === "string" &&
    sessionRun.active_plan_relpath.trim()
      ? sessionRun.active_plan_relpath.trim()
      : "plan.md";

  useEffect(() => {
    if (!showPlanApproval || !sessionId) return;
    openPlanApprovalWorkbenchRef?.current?.(activePlanRelpath);
  }, [
    showPlanApproval,
    sessionId,
    planMd,
    activePlanRelpath,
    openPlanApprovalWorkbenchRef,
  ]);

  const planWorkflowAwaitingApproval =
    isPlanWorkflowAwaitingApproval(planWorkflow);
  const composerInputLocked = waitingForSession;
  const preflightBlocked = selected.some((id) => {
    const row = healthAgents.find((a) => a.id === id);
    return Boolean(row && !row.ready);
  });
  const customWorkspaceBlocked =
    isNew && workspaceId === CUSTOM_WORKSPACE_ID && !workspacePath?.trim();
  const composerSendLocked =
    runBusy ||
    running ||
    synthesizing ||
    (loading && waitingForSession) ||
    selected.length === 0 ||
    preflightBlocked ||
    customWorkspaceBlocked ||
    planWorkflowAwaitingApproval ||
    (!text.trim() && pendingFiles.length === 0);

  const firstOpenBlock = useMemo<RoomObjection | null>(() => {
    const rows = roomTasks?.open_objections ?? [];
    return rows.find((o) => o.act === "BLOCK") ?? null;
  }, [roomTasks?.open_objections]);

  const planExecuteObjection = planExecute.openObjectionBlock?.objections[0];
  const composerObjectionNotice = tweaks.objectionDemo
    ? DEMO_OBJECTION_NOTICE
    : planExecuteObjection
      ? {
          message:
            planExecute.openObjectionBlock?.message ??
            "미해결 이의가 있습니다.",
          objectionId: planExecuteObjection.id,
          actionIndex: planExecuteObjection.plan_action_index,
        }
      : null;

  const composerPlaceholder = planWorkflowAwaitingApproval
    ? localeMsg.planWorkflowComposerBlocked
    : firstOpenBlock?.plan_action_index
      ? locale === "ko"
        ? `plan #${firstOpenBlock.plan_action_index} BLOCK 해결 후 execute`
        : `Resolve plan #${firstOpenBlock.plan_action_index} BLOCK before execute`
      : localeMsg.composerPlaceholder;

  return {
    workspaceAutoContext: {
      hasPendingExecution,
      hasDryRunDiff,
      hasBlocker,
    },
    consensusBlocked,
    showExecuteQueueStrip,
    demoExecPending,
    execPendingForBar,
    consensusForBar,
    showConsensusDryRunGate,
    planWorkflow,
    planWorkflowPlanIntent,
    planWorkflowActive,
    showPlanApproval,
    showPlanWorkflowBanner,
    showPlanWorkflowComposerHint,
    planWorkflowAwaitingApproval,
    activePlanRelpath,
    composerInputLocked,
    composerSendLocked,
    firstOpenBlock,
    composerObjectionNotice,
    composerPlaceholder,
    executeBusy: planExecute.busy,
    planExecutions: planExecute.executions,
    executeError: planExecute.error,
  };
}
