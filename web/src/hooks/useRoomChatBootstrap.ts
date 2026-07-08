/** Room session + plan shell bootstrap (F9 P2). */
import { useEffect, useRef, useState } from "react";
import type { RoomChatProps } from "./roomChatTypes";
import { useInboxState } from "./useInboxState";
import { useGoalLoop } from "./useGoalLoop";
import { useRoomPlanShellState } from "./useRoomPlanShellState";
import { bindRoomSessionRefreshCommands, useRoomSessionSync } from "./useRoomSessionSync";
import { useRoomComposerPrefs } from "./useRoomComposerPrefs";
import { useRoomRunWatchdog } from "./useRoomRunWatchdog";
import { useRoomSlashCommands } from "./useRoomSlashCommands";
import { useHumanDecisionRuntime } from "./useHumanDecisionRuntime";
import type { PendingFile } from "../components/ChatComposer";
import { type WorkFocusTarget } from "../components/WorkToolPanel";
import { useMacNotifications } from "./useMacNotifications";
import { usePlanExecute } from "./usePlanExecute";
import { useLocale } from "../i18n/useLocale";
import { useRoomWorkspace } from "./useRoomWorkspace";
import { useRoomAgentCapabilities } from "./useRoomAgentCapabilities";
import { useRoomConsensusHandlers } from "./useRoomConsensusHandlers";
import { useTweaksDemoOptional } from "./useTweaksDemo";
import { TWEAKS_DEMO_OFF } from "../context/tweaksDemoStore";

export function useRoomChatBootstrap(props: RoomChatProps) {
  const {
    agents,
    healthAgents = [],
    teamHealthAgents = [],
    sessionId,
    session,
    loading,
    onSessionChange,
    onSessionMetaRefresh,
    bootstrapAgentIds,
    bootstrapTopic,
    bootstrapMissionTemplateId,
    onBootstrapAgentsApplied,
  } = props;
  const { push: pushMacNotification } = useMacNotifications();
  const pendingMissionTemplateRef = useRef<string | null>(
    bootstrapMissionTemplateId ?? null,
  );
  useEffect(() => {
    if (bootstrapMissionTemplateId) {
      pendingMissionTemplateRef.current = bootstrapMissionTemplateId;
    }
  }, [bootstrapMissionTemplateId]);
  const tweaks = useTweaksDemoOptional() ?? TWEAKS_DEMO_OFF;
  const [selected, setSelected] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const {
    messages,
    running,
    runBusy,
    synthesizing,
    localSseRun,
    runStartedAt,
    topologyActive,
    topologyDone,
    setLiveRunSessionKey,
    activeSessionIdRef,
    navigatedToSessionRef,
    pendingSessionRoomModelsRef,
    agentsPickerInitRef,
    refreshCommandsRef,
    roomTasks,
    planMd,
    readiness,
    setReadiness,
    isNew,
    waitingForSession,
    refreshSessionMeta,
    persistPendingSessionRoomModels,
  } = useRoomSessionSync({
    sessionId,
    session,
    loading,
    selected,
    agents,
    healthAgents,
    teamHealthAgents,
    bootstrapAgentIds,
    bootstrapTopic,
    onBootstrapAgentsApplied,
    onSessionChange,
    onSessionMetaRefresh,
    setSelected,
    setText,
    setPendingFiles,
  });
  const {
    longRunning,
    runLockStuck,
    setRunLockStuck,
    releasingLock,
    setReleasingLock,
    clearRunWatchdog,
    clearLongRunHint,
    scheduleLongRunHint,
    armStopWatchdog,
  } = useRoomRunWatchdog(sessionId);
  const [planActionFocusIndex, setPlanActionFocusIndex] = useState<
    number | null
  >(null);
  const [workHookAlert, setWorkHookAlert] = useState<{
    event: string;
    body: string;
    blocked: boolean;
  } | null>(null);
  const [composerNoticeDismissed, setComposerNoticeDismissed] = useState<
    string | null
  >(null);
  const openInspectorRef = useRef<() => void>(() => {});
  const [permOpen, setPermOpen] = useState(false);
  const [researchMode] = useState(() => {
    try {
      return localStorage.getItem("agent-lab-research-mode") === "1";
    } catch {
      return false;
    }
  });
  const { locale, msg: localeMsg } = useLocale();
  const {
    turnProfile,
    roomPreset,
    forceRoomPreset,
    resolvedRoomPresets,
    composerModeVariant,
    composerPresetHint,
    composerRoutingHint,
    composerEmergenceHint,
    composerCostHint,
  } = useRoomComposerPrefs({
    sessionRoomPreset:
      typeof session?.run?.room_preset === "string"
        ? session.run.room_preset
        : null,
    locale,
    healthAgents,
    selectedAgents: selected,
    sessionRun: session?.run as Record<string, unknown> | undefined,
    draftTopic: text,
  });

  // §3.2.1: fast is single-agent — promote to supervisor when roster > 1 (no silent truncate).
  useEffect(() => {
    if (roomPreset === "fast" && selected.length > 1) {
      forceRoomPreset("supervisor");
    }
  }, [forceRoomPreset, roomPreset, selected.length]);

  const [pendingSend, setPendingSend] = useState<{
    text: string;
    files: PendingFile[];
  } | null>(null);
  const lastPlainSendTextRef = useRef<string | null>(null);
  const [sendReceipt, setSendReceipt] = useState<string | null>(null);
  const [sendReceiptRaw, setSendReceiptRaw] = useState<string | undefined>();
  const [discussPaused, setDiscussPaused] = useState(false);
  const [workFocus, setWorkFocus] = useState<WorkFocusTarget | null>(null);
  const sendReceiptTimerRef = useRef<number | null>(null);
  const [clarifierQuestions, setClarifierQuestions] = useState<string[] | null>(
    null,
  );
  const [clarifierInterview, setClarifierInterview] = useState<{
    questions?: { id?: string; category?: string; prompt?: string }[];
    plan_mode?: boolean;
  } | null>(null);
  const {
    slashCommands,
    setSlashCommands,
    commandHint,
    setCommandHint,
    authRun,
    setAuthRun,
    secretCommand,
    setSecretCommand,
    secretValue,
    setSecretValue,
    commandChoices,
    setCommandChoices,
    commandChoiceIndex,
    setCommandChoiceIndex,
    commandMultiChoices,
    setCommandMultiChoices,
    commandScopeChoices,
    setCommandScopeChoices,
    multiSelected,
    setMultiSelected,
    modelPopover,
    setModelPopover,
    externalCommandConfirm,
    setExternalCommandConfirm,
    refreshCommands,
  } = useRoomSlashCommands({ sessionId, activeSessionIdRef });
  bindRoomSessionRefreshCommands(refreshCommandsRef, refreshCommands);
  const runAbortRef = useRef<AbortController | null>(null);
  const { workspaceId, workspacePath } = useRoomWorkspace(sessionId);
  const { agentCapabilities } = useRoomAgentCapabilities({
    sessionId,
    sessionRun: session?.run as Record<string, unknown> | undefined,
    selected,
    pendingSessionRoomModelsRef,
    agentsPickerInitRef,
    setSelected,
  });

  const {
    inboxPendingCount,
    inboxReloadKey,
    setInboxReloadKey,
    refreshInboxPending,
    syncInboxPendingCount,
  } = useInboxState(sessionId);

  const {
    setGoalText,
    setGoalError,
    verifiedEditGoal,
    verifiedEditCriteria,
    verifiedEditPromise,
    verifiedLoopBusy,
    setVerifiedLoopBusy,
    verifiedLoopError,
    setVerifiedLoopError,
    verifiedLoopView,
  } = useGoalLoop(sessionId, session?.run, refreshSessionMeta);

  const { runtime: decisionRuntime } = useHumanDecisionRuntime(
    sessionId,
    inboxReloadKey,
    discussPaused,
  );

  const openPlanApprovalWorkbenchRef = useRef<
    ((relpath: string) => void) | null
  >(null);

  const planExecute = usePlanExecute({
    sessionId,
    run: session?.run,
    onUpdated: refreshSessionMeta,
  });

  const {
    consensusProposal,
    setConsensusProposal,
    consensusGateBusy,
    notifyConsensusSync,
    notifyConsensusFailure,
    handleConsensusDryRun,
    dismissConsensusProposal,
    composerPlanStale,
  } = useRoomConsensusHandlers({
    sessionId,
    sessionRun: session?.run as Record<string, unknown> | undefined,
    turnProfile,
    running,
    runBusy,
    synthesizing,
    planExecute,
    pushMacNotification,
    refreshSessionMeta,
    setInboxReloadKey,
  });

  const planShell = useRoomPlanShellState({
    sessionId,
    sessionRun: session?.run,
    planMd,
    roomTasks,
    planExecute,
    consensusProposal,
    verifiedLoopPendingApproval: verifiedLoopView.pendingApproval,
    tweaks: {
      execQueueDemo: tweaks.execQueueDemo,
      consensusGateDemo: tweaks.consensusGateDemo,
      objectionDemo: tweaks.objectionDemo,
    },
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
  });

  const {
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
    composerInputLocked,
    composerSendLocked,
    firstOpenBlock,
    composerObjectionNotice,
    composerPlaceholder,
    executeBusy,
    planExecutions,
  } = planShell;

  return {
    props,
    pushMacNotification,
    pendingMissionTemplateRef,
    tweaks,
    selected, setSelected,
    text, setText,
    pendingFiles, setPendingFiles,
    messages, running, runBusy, synthesizing, localSseRun, runStartedAt,
    topologyActive, topologyDone, setLiveRunSessionKey, activeSessionIdRef,
    navigatedToSessionRef, pendingSessionRoomModelsRef, agentsPickerInitRef,
    refreshCommandsRef, roomTasks, planMd, readiness, setReadiness, isNew,
    waitingForSession, refreshSessionMeta, persistPendingSessionRoomModels,
    longRunning, runLockStuck, setRunLockStuck, releasingLock, setReleasingLock,
    clearRunWatchdog, clearLongRunHint, scheduleLongRunHint, armStopWatchdog,
    planActionFocusIndex, setPlanActionFocusIndex, workHookAlert, setWorkHookAlert,
    composerNoticeDismissed, setComposerNoticeDismissed, openInspectorRef, permOpen, setPermOpen,
    researchMode, locale, localeMsg, turnProfile, roomPreset,
    forceRoomPreset, resolvedRoomPresets, composerModeVariant,
    composerPresetHint, composerRoutingHint, composerEmergenceHint, composerCostHint, pendingSend, setPendingSend,
    lastPlainSendTextRef, sendReceipt, setSendReceipt, sendReceiptRaw, setSendReceiptRaw,
    discussPaused, setDiscussPaused, workFocus, setWorkFocus, sendReceiptTimerRef,
    clarifierQuestions, setClarifierQuestions, clarifierInterview, setClarifierInterview,
    slashCommands, setSlashCommands, commandHint, setCommandHint, authRun, setAuthRun,
    secretCommand, setSecretCommand, secretValue, setSecretValue, commandChoices, setCommandChoices,
    commandChoiceIndex, setCommandChoiceIndex, commandMultiChoices, setCommandMultiChoices,
    commandScopeChoices, setCommandScopeChoices, multiSelected, setMultiSelected,
    modelPopover, setModelPopover, externalCommandConfirm, setExternalCommandConfirm,
    refreshCommands, runAbortRef, workspaceId, workspacePath, agentCapabilities,
    inboxPendingCount, inboxReloadKey, setInboxReloadKey, refreshInboxPending, syncInboxPendingCount,
    setGoalText, setGoalError, verifiedEditGoal, verifiedEditCriteria, verifiedEditPromise,
    verifiedLoopBusy, setVerifiedLoopBusy, verifiedLoopError, setVerifiedLoopError, verifiedLoopView,
    decisionRuntime, openPlanApprovalWorkbenchRef, planExecute,
    consensusProposal, setConsensusProposal, consensusGateBusy, notifyConsensusSync,
    notifyConsensusFailure, handleConsensusDryRun, dismissConsensusProposal, composerPlanStale,
    planShell, consensusBlocked, showExecuteQueueStrip, demoExecPending, execPendingForBar,
    consensusForBar, showConsensusDryRunGate, planWorkflow, planWorkflowPlanIntent, planWorkflowActive,
    showPlanApproval, showPlanWorkflowBanner, showPlanWorkflowComposerHint, composerInputLocked,
    composerSendLocked, firstOpenBlock, composerObjectionNotice, composerPlaceholder, executeBusy, planExecutions,
  };
}
