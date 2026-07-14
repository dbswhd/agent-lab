import { useMemo, type ComponentProps } from "react";
import type {
  AgentOption,
  PlanExecutionRecord,
  PlanWorkflowRecord,
  SessionDetail,
} from "../api/client";
import { ComposerEventStack } from "../components/ComposerEventStack";
import type {
  PlanApprovalMode,
  PlanRejectPayload,
} from "../components/PlanApprovalPanel";
import type { ConsensusDryRunProposal } from "../components/ConsensusDryRunGateBar";
import type { WorkFocusTarget } from "../components/WorkToolPanel";
import type { PlanMetaView } from "../utils/planMeta";
import type { StoredPlanAction } from "../utils/planExecuteHistory";
import type { RoomTasksPayload } from "../api/client";

export type ComposerEventStackProps = ComponentProps<typeof ComposerEventStack>;

type MacNotificationPayload = {
  title: string;
  body?: string;
};

type PlanExecuteSlice = {
  error: string | null | undefined;
  hasExecutableActions: boolean;
  canDryRun: boolean;
  approve: () => void;
  reject: () => void;
  reverify: (executionId: string) => void;
  dryRun: (overrideKey?: string | null) => Promise<boolean>;
};

type WorkHookAlert = {
  event: string;
  body: string;
  blocked: boolean;
};

export type RoomComposerEventStackOptions = {
  sessionId: string | null;
  session: SessionDetail | null;
  planMd: string;
  planMeta: PlanMetaView;
  workPlanStaleNotice: string | null;
  workFocus: WorkFocusTarget | null;
  setWorkFocus: (value: WorkFocusTarget | null) => void;
  synthesizing: boolean;
  running: boolean;
  runBusy: boolean;
  executeBusy: boolean;
  handleSynthesizeNow: () => void;
  handlePlanRefClick: (line: number) => void;
  focusTask: (taskId: string) => void;
  focusObjection: (id: string, actionIndex?: number) => void;
  refreshSessionMeta: () => void;
  roomTasks: RoomTasksPayload | null;
  agents: AgentOption[];
  planExecute: PlanExecuteSlice;
  planWorkflow: PlanWorkflowRecord | undefined;
  showPlanApproval: boolean;
  verifiedLoopBusy: boolean;
  verifiedLoopError: string | null;
  handleVerifiedApprove: (mode: PlanApprovalMode) => void | Promise<void>;
  handleVerifiedReject: (payload?: PlanRejectPayload) => void | Promise<void>;
  workHookAlert: WorkHookAlert | null;
  setWorkHookAlert: (value: WorkHookAlert | null) => void;
  inboxPendingCount: number;
  inboxReloadKey: number;
  currentPlanRevision: string | null;
  handleInboxResolved: () => void;
  handleInboxBuildStarted: () => void;
  handleInboxRefClick: (ref: string) => void;
  execPendingForBar: PlanExecutionRecord | null;
  demoExecPending: PlanExecutionRecord | null;
  showExecuteQueueStrip: boolean;
  consensusForBar: ConsensusDryRunProposal | null;
  showConsensusDryRunGate: boolean;
  consensusGateBusy: boolean;
  consensusGateDemo: boolean;
  setConsensusGateDemo: (value: boolean) => void;
  handleConsensusDryRun: () => void;
  dismissConsensusProposal: () => void;
  openDiffTab: () => void;
  openFilesTab: () => void;
  openFileInWorkbench: (path: string) => void;
  pushMacNotification: (payload: MacNotificationPayload) => void;
};

/** ComposerEventStack props assembly — extracted from RoomChat (F9). */
export function useRoomComposerEventStack(
  options: RoomComposerEventStackOptions,
): ComposerEventStackProps | null {
  const {
    sessionId,
    session,
    planMd,
    planMeta,
    workPlanStaleNotice,
    workFocus,
    setWorkFocus,
    synthesizing,
    running,
    runBusy,
    executeBusy,
    handleSynthesizeNow,
    handlePlanRefClick,
    focusTask,
    focusObjection,
    refreshSessionMeta,
    roomTasks,
    agents,
    planExecute,
    planWorkflow,
    showPlanApproval,
    verifiedLoopBusy,
    verifiedLoopError,
    handleVerifiedApprove,
    handleVerifiedReject,
    workHookAlert,
    setWorkHookAlert,
    inboxPendingCount,
    inboxReloadKey,
    currentPlanRevision,
    handleInboxResolved,
    handleInboxBuildStarted,
    handleInboxRefClick,
    execPendingForBar,
    demoExecPending,
    showExecuteQueueStrip,
    consensusForBar,
    showConsensusDryRunGate,
    consensusGateBusy,
    consensusGateDemo,
    setConsensusGateDemo,
    handleConsensusDryRun,
    dismissConsensusProposal,
    openDiffTab,
    openFilesTab,
    openFileInWorkbench,
    pushMacNotification,
  } = options;

  return useMemo(() => {
    if (!sessionId) return null;
    return {
      sessionId,
      session,
      planMd,
      planMeta,
      planStaleNotice: workPlanStaleNotice,
      workFocus,
      onWorkFocusHandled: () => setWorkFocus(null),
      synthesizing,
      running,
      runBusy,
      executeBusy,
      onSynthesizeNow: handleSynthesizeNow,
      onPlanRefClick: handlePlanRefClick,
      onFocusTask: focusTask,
      onFocusObjection: focusObjection,
      onSessionUpdated: refreshSessionMeta,
      roomTasks,
      cursorReady: agents.some((a) => a.id === "cursor" && a.ready),
      executeError: planExecute.error,
      onRetryExecute: () => void planExecute.dryRun(),
      planWorkflow,
      planApproval: showPlanApproval
        ? {
            enabled: true,
            workflowNotice: planWorkflow?.notice,
            planGate: planWorkflow?.last_plan_gate ?? null,
            canExecute:
              planExecute.hasExecutableActions &&
              planExecute.canDryRun &&
              agents.some((agent) => agent.id === "cursor" && agent.ready),
            busy: verifiedLoopBusy || running || runBusy,
            error: verifiedLoopError,
            onApprove: (mode: PlanApprovalMode) =>
              void handleVerifiedApprove(mode),
            onReject: (payload?: PlanRejectPayload) =>
              void handleVerifiedReject(payload),
          }
        : null,
      workHookAlert,
      onDismissWorkHookAlert: () => setWorkHookAlert(null),
      inboxPendingCount,
      inboxReloadKey,
      currentPlanRevision,
      onInboxResolved: handleInboxResolved,
      onInboxBuildStarted: handleInboxBuildStarted,
      onInboxRefClick: handleInboxRefClick,
      execPending: execPendingForBar,
      storedActions: (session?.run?.actions as StoredPlanAction[]) ?? [],
      onExecuteApprove: () => {
        if (demoExecPending) {
          pushMacNotification({
            title: "Execute (demo)",
            body: "승인 시뮬레이트",
          });
          return;
        }
        void planExecute.approve();
      },
      onExecuteReject: () => {
        if (demoExecPending) {
          pushMacNotification({
            title: "Execute (demo)",
            body: "거부 시뮬레이트",
          });
          return;
        }
        void planExecute.reject();
      },
      onExecuteReverify: (executionId: string) => {
        if (demoExecPending) {
          pushMacNotification({
            title: "Execute (demo)",
            body: "재검증 시뮬레이트",
          });
          return;
        }
        void planExecute.reverify(executionId);
      },
      showExecuteQueue: showExecuteQueueStrip,
      consensusProposal: consensusForBar,
      showConsensusGate: showConsensusDryRunGate,
      consensusGateBusy,
      onConsensusDryRun: consensusGateDemo
        ? () =>
            pushMacNotification({
              title: "Consensus (demo)",
              body: "Dry-run 시뮬레이트",
            })
        : handleConsensusDryRun,
      onConsensusDismiss: consensusGateDemo
        ? () => setConsensusGateDemo(false)
        : dismissConsensusProposal,
      onOpenDiff: openDiffTab,
      onOpenFiles: openFilesTab,
      onOpenFile: openFileInWorkbench,
      disabled: running || synthesizing || runBusy,
    };
  }, [
    sessionId,
    session,
    planMd,
    planMeta,
    workPlanStaleNotice,
    workFocus,
    setWorkFocus,
    synthesizing,
    running,
    runBusy,
    executeBusy,
    handleSynthesizeNow,
    handlePlanRefClick,
    focusTask,
    focusObjection,
    refreshSessionMeta,
    roomTasks,
    agents,
    planExecute,
    planWorkflow,
    showPlanApproval,
    verifiedLoopBusy,
    verifiedLoopError,
    handleVerifiedApprove,
    handleVerifiedReject,
    workHookAlert,
    setWorkHookAlert,
    inboxPendingCount,
    inboxReloadKey,
    currentPlanRevision,
    handleInboxResolved,
    handleInboxBuildStarted,
    handleInboxRefClick,
    execPendingForBar,
    demoExecPending,
    showExecuteQueueStrip,
    consensusForBar,
    showConsensusDryRunGate,
    consensusGateBusy,
    consensusGateDemo,
    setConsensusGateDemo,
    handleConsensusDryRun,
    dismissConsensusProposal,
    openDiffTab,
    openFilesTab,
    openFileInWorkbench,
    pushMacNotification,
  ]);
}
