/** Room workspace orchestrator — hooks, handlers, derived view model (F9 slice 4d). */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AgentOption, SessionDetail } from "../api/client";
import {
  cancelRoomRun,
  matchSlashCommand,
  pauseMissionLoop,
  type AgentHealthRow,
} from "../api/client";
import { useInboxState } from "../hooks/useInboxState";
import { useGoalLoop } from "../hooks/useGoalLoop";
import { useWorkspaceTabs } from "../hooks/useWorkspaceTabs";
import { useRoomPlanShellState } from "../hooks/useRoomPlanShellState";
import { useRoomTranscriptView } from "../hooks/useRoomTranscriptView";
import {
  bindRoomSessionRefreshCommands,
  useRoomSessionSync,
} from "../hooks/useRoomSessionSync";
import {
  finalizeCancelledTyping,
  getRunningSessionIds,
  resolveRunSessionKey,
} from "../run/runSessionRegistry";
import {
  getLastRightPanelMode,
  setLastRightPanelMode,
} from "../utils/inspectorPanePrefs";
import { useRoomWorkbenchLayout } from "../hooks/useRoomWorkbenchLayout";
import { useRoomComposerPrefs } from "../hooks/useRoomComposerPrefs";
import { useRoomRunWatchdog } from "../hooks/useRoomRunWatchdog";
import {
  discussRecoveryFromMissionLoop,
  useRoomRecoveryLifecycle,
} from "../hooks/useRoomRecoveryLifecycle";
import { useAutonomySession } from "../hooks/useAutonomySession";
import { useRoomSlashCommands } from "../hooks/useRoomSlashCommands";
import { useHumanDecisionRuntime } from "../hooks/useHumanDecisionRuntime";
import type { PendingFile } from "../components/ChatComposer";
import { type WorkFocusTarget } from "../components/WorkToolPanel";
import { useMacNotifications } from "../hooks/useMacNotifications";
import {
  agentsNeedingPermissionPrompt,
  hasSavedPermissionDefaults,
  roomPermissions,
} from "../utils/agentPermissions";
import { dispatchNotification } from "../utils/pushNotification";
import { notifyDesktop } from "../utils/desktopNotify";
import { buildPlanMetaView } from "../utils/planMeta";
import { buildGoalLoopView } from "../utils/goalLoopView";
import { activateInboxRef } from "../utils/inboxRefNavigation";
import { focusComposerStack } from "../utils/composerStackFocus";
import { type ComposerTurnProfile } from "../utils/turnProfile";
import { usePlanExecute } from "../hooks/usePlanExecute";
import { useLocale } from "../i18n/useLocale";
import { useRoomExecuteSend } from "../hooks/useRoomExecuteSend";
import { useRoomComposerPopovers } from "../hooks/useRoomComposerPopovers";
import { useRoomComposerEventStack } from "../hooks/useRoomComposerEventStack";
import { useRoomSlashExecute } from "../hooks/useRoomSlashExecute";
import { useRoomWorkspace } from "../hooks/useRoomWorkspace";
import { useRoomAgentCapabilities } from "../hooks/useRoomAgentCapabilities";
import { useRoomConsensusHandlers } from "../hooks/useRoomConsensusHandlers";
import { useRoomVerifiedHandlers } from "../hooks/useRoomVerifiedHandlers";
import {
  useRoomRecoveryActions,
  useRoomRecoveryNotifications,
} from "../hooks/useRoomRecoveryHandlers";
import { useRoomNotificationRouting } from "../hooks/useRoomNotificationRouting";
import { useRoomPaletteActions } from "../hooks/useRoomPaletteActions";
import { type AgentThreadBindings } from "../utils/agentThreadBindings";
import { useTweaksDemoOptional } from "../hooks/useTweaksDemo";
import { TWEAKS_DEMO_OFF } from "../context/tweaksDemoStore";
import { DEMO_PLAN_STALE_NOTICE } from "../utils/tweaksDemoFixtures";


export type RoomChatProps = {
  agents: AgentOption[];
  apiOk?: boolean;
  healthAgents?: AgentHealthRow[];
  /** Configured room composition subset (for default agent selection). */
  teamHealthAgents?: AgentHealthRow[];
  sessionId: string | null;
  session: SessionDetail | null;
  loading?: boolean;
  onSessionChange: (sessionId: string) => void | Promise<void>;
  /** Sidebar/list only — no full session fetch (use during SSE start). */
  onSessionBind?: (sessionId: string) => void | Promise<void>;
  /** run.json / plan.md only — must not reset chat messages */
  onSessionMetaRefresh?: (sessionId: string) => void | Promise<void>;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  onOpenSettings?: () => void;
  onRefreshHealth?: () => void | Promise<void>;
  /** Agent ids chosen in NewSessionDialog — applied once on isNew mount. */
  bootstrapAgentIds?: string[] | null;
  /** Per-agent resume bindings from NewSessionDialog (new sessions only). */
  bootstrapAgentThreadBindings?: AgentThreadBindings | null;
  bootstrapSessionTemplate?: string | null;
  bootstrapTopic?: string | null;
  /** Mission OS template — applied once when session folder is created. */
  bootstrapMissionTemplateId?: string | null;
  onBootstrapAgentsApplied?: () => void;
  onBootstrapMissionTemplateApplied?: () => void;
};

export function useRoomChat(props: RoomChatProps) {
  const {
    agents,
    apiOk = true,
    healthAgents = [],
    teamHealthAgents = [],
    sessionId,
    session,
    loading,
    onSessionChange,
    onSessionBind,
    onSessionMetaRefresh,
    sidebarOpen,
    onToggleSidebar,
    onOpenSettings,
    onRefreshHealth,
    bootstrapAgentIds,
    bootstrapAgentThreadBindings,
    bootstrapSessionTemplate,
    bootstrapTopic,
    bootstrapMissionTemplateId,
    onBootstrapAgentsApplied,
    onBootstrapMissionTemplateApplied,
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
    selectRoomPreset,
    forceRoomPreset,
    resolvedRoomPresets,
    visiblePresets,
    composeMode,
    composerModeVariant,
    composerPresetHint,
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
    turnProfile: ComposerTurnProfile;
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

  const openInspectorPane = useCallback(() => {
    openInspectorRef.current();
  }, []);

  const {
    rightPanelMode,
    setWorkspaceTab,
    setRightPanelMode,
    openWorkTab,
    openPlanTab,
    openTranscriptTab,
    openDiffTab,
    openFilesTab,
    focusWorkStack,
  } = useWorkspaceTabs({
    sessionKey: sessionId ?? "new",
    isNew: !sessionId,
    initialRightPanelMode: getLastRightPanelMode(),
    onToolRequested: openInspectorPane,
    autoContext: {
      running,
      ...planShell.workspaceAutoContext,
      planMd,
    },
  });

  const {
    inspectorOpen,
    workbenchMenuOpen,
    setWorkbenchMenuOpen,
    filesFocusRevision,
    setFilesFocusRevision,
    filesFocusPath,
    setFilesFocusPath,
    workbenchPanelWidth,
    openInspectorPane: openWorkbenchInspector,
    toggleInspector,
    setActiveWorkbenchWidth,
    commitWorkbenchWidth,
    resetWorkbenchWidthForMode,
  } = useRoomWorkbenchLayout(rightPanelMode);

  openPlanApprovalWorkbenchRef.current = (relpath: string) => {
    setFilesFocusPath(relpath);
    setFilesFocusRevision((n) => n + 1);
    openFilesTab();
  };

  openInspectorRef.current = openWorkbenchInspector;

  useEffect(() => {
    setLastRightPanelMode(rightPanelMode);
  }, [rightPanelMode]);

  const handleSelectRightPanelMode = useCallback(
    (mode: typeof rightPanelMode) => {
      setRightPanelMode(mode);
      resetWorkbenchWidthForMode(mode);
    },
    [resetWorkbenchWidthForMode, setRightPanelMode],
  );

  const openHumanInbox = useCallback(() => {
    focusComposerStack("inbox");
  }, []);

  const openWorkApproval = useCallback(() => {
    focusWorkStack("plan_approval");
  }, [focusWorkStack]);

  const handleInboxBuildStarted = useCallback(() => {
    focusWorkStack("execute");
    refreshSessionMeta();
    if (sessionId) {
      dispatchNotification(
        {
          tier: "P2",
          title: "Build 실행 시작",
          body: "Composer에서 진행 상황을 확인하세요.",
          sessionId,
          kind: "human_inbox_build",
          toastAction: { type: "composer", focus: "plan" },
        },
        pushMacNotification,
        notifyDesktop,
      );
    }
  }, [focusWorkStack, refreshSessionMeta, sessionId, pushMacNotification]);

  const handleInboxResolved = useCallback(
    (detail?: { pendingCount?: number }) => {
      if (typeof detail?.pendingCount === "number") {
        syncInboxPendingCount(detail.pendingCount);
      }
      void refreshInboxPending();
      refreshSessionMeta();
      setDiscussPaused(false);
    },
    [refreshInboxPending, refreshSessionMeta, syncInboxPendingCount],
  );

  const { handleNotificationOpen } = useRoomNotificationRouting({
    focusWorkStack,
    setRightPanelMode,
    onOpenSettings,
  });

  const transcript = useRoomTranscriptView({
    sessionId,
    sessionRun: session?.run,
    sessionChat: session?.chat,
    messages,
    roomTasks,
    running,
    localSseRun,
    topologyActive,
    topologyDone,
    turnProfile,
    selected,
    openTranscriptTab,
    focusWorkStack,
  });

  useEffect(() => {
    if (planActionFocusIndex == null) {
      return;
    }
    focusWorkStack("plan");
    const timer = window.setTimeout(() => {
      setPlanActionFocusIndex(null);
    }, 80);
    return () => window.clearTimeout(timer);
  }, [planActionFocusIndex, focusWorkStack]);

  useEffect(() => {
    setGoalText(buildGoalLoopView(session?.run).goal.text ?? "");
    setGoalError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, JSON.stringify(session?.run?.session_goal)]);

  const goalView = useMemo(
    () => buildGoalLoopView(session?.run),
    [session?.run],
  );

  const openFileInWorkbench = useCallback(
    (path: string) => {
      const trimmed = path.trim();
      if (!trimmed) return;
      setFilesFocusPath(trimmed);
      setFilesFocusRevision((n) => n + 1);
      openFilesTab();
    },
    [openFilesTab],
  );

  const avoidWorkbenchNotice = inspectorOpen || workbenchMenuOpen;

  const { notifyRecoveryResolution, notifyRecoveryStarted } =
    useRoomRecoveryNotifications({
      sessionId,
      pushMacNotification,
    });

  const discussRecovery = useMemo(
    () => discussRecoveryFromMissionLoop(session?.run?.mission_loop),
    [session?.run?.mission_loop],
  );

  const {
    setRecoveryFailure,
    recoveryItems,
    recoveryLifecycleView,
    recoverySignature,
    recoveryVisible,
    setRecoveryDismissedSig,
    discussRecoveryBusy,
    setDiscussRecoveryBusy,
    recoveryBusyAction,
    setRecoveryBusyAction,
    beginRecoveryAttempt,
    finishRecoveryAction,
  } = useRoomRecoveryLifecycle({
    sessionId,
    apiOk,
    healthAgents,
    readiness,
    selectedAgentIds: selected,
    runLockStuck,
    discussRecovery,
    executeError: planShell.executeError,
    planExecutions: planExecutions,
    composerSendLocked,
    onResolutionNotify: notifyRecoveryResolution,
  });

  function addFiles(fileList: FileList | File[]) {
    const next: PendingFile[] = [];
    for (const f of Array.from(fileList)) {
      next.push({ id: `${f.name}-${f.size}-${Date.now()}`, file: f });
    }
    setPendingFiles((prev) => [...prev, ...next]);
  }

  const handleStop = useCallback(() => {
    const runningIds = getRunningSessionIds();
    const primaryId = sessionId ?? runningIds[0] ?? null;
    const keys = new Set<string>();
    for (const id of runningIds) {
      keys.add(resolveRunSessionKey(id, id));
      void pauseMissionLoop(id, { reason: "global_cancel" }).catch(() => {});
    }
    if (primaryId) {
      keys.add(resolveRunSessionKey(primaryId, primaryId));
      if (!runningIds.includes(primaryId)) {
        void pauseMissionLoop(primaryId, { reason: "global_cancel" }).catch(
          () => {},
        );
      }
    }
    for (const key of keys) {
      finalizeCancelledTyping(key);
    }
    void (async () => {
      try {
        await cancelRoomRun(primaryId ?? undefined);
        if (primaryId && onSessionMetaRefresh) {
          await onSessionMetaRefresh(primaryId);
        }
      } catch {
        /* still abort local SSE */
      }
      runAbortRef.current?.abort();
    })();
    armStopWatchdog();
  }, [armStopWatchdog, sessionId, onSessionMetaRefresh]);

  const {
    applySessionScopedModels,
    executeSlashCommand,
    handleAuthRunComplete,
    runSlashCommand,
  } = useRoomSlashExecute({
    sessionId,
    activeSessionIdRef,
    agents,
    slashCommands,
    authRun,
    commandChoices,
    commandChoiceIndex,
    setCommandHint,
    setCommandChoices,
    setCommandScopeChoices,
    setCommandMultiChoices,
    setModelPopover,
    setMultiSelected,
    setAuthRun,
    setSecretCommand,
    setSecretValue,
    setExternalCommandConfirm,
    setSlashCommands,
    setCommandChoiceIndex,
    setSelected,
    setText,
    pendingSessionRoomModelsRef,
    agentsPickerInitRef,
    refreshSessionMeta,
    onRefreshHealth,
    handleStop,
  });

  useEffect(() => {
    if (isNew) return;
    function onKeyDown(event: KeyboardEvent) {
      if (!event.metaKey || event.altKey) return;
      if (event.ctrlKey && event.key.toLowerCase() === "i") {
        event.preventDefault();
        toggleInspector();
        return;
      }
      if (!event.ctrlKey && !event.shiftKey && event.key === "." && running) {
        event.preventDefault();
        handleStop();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isNew, toggleInspector, running, handleStop]);

  const { executeSend } = useRoomExecuteSend({
    sessionId,
    selected,
    runBusy,
    running,
    synthesizing,
    composeMode,
    turnProfile,
    roomPreset,
    resolvedRoomPresets,
    researchMode,
    workspaceId,
    workspacePath,
    agentCapabilities,
    bootstrapAgentThreadBindings,
    bootstrapSessionTemplate,
    locale,
    localeMsg,
    onSessionChange,
    onSessionBind,
    onSessionMetaRefresh,
    onBootstrapMissionTemplateApplied,
    refreshSessionMeta,
    persistPendingSessionRoomModels,
    clearRunWatchdog,
    scheduleLongRunHint,
    clearLongRunHint,
    openPlanTab,
    notifyConsensusSync,
    notifyConsensusFailure,
    pushMacNotification,
    refreshInboxPending,
    openHumanInbox,
    openWorkTab,
    activeSessionIdRef,
    navigatedToSessionRef,
    pendingMissionTemplateRef,
    pendingSessionRoomModelsRef,
    runAbortRef,
    sendReceiptTimerRef,
    lastPlainSendTextRef,
    setPendingFiles,
    setLiveRunSessionKey,
    setRecoveryFailure,
    setRunLockStuck,
    setClarifierQuestions,
    setClarifierInterview,
    setDiscussPaused,
    setInboxReloadKey,
    setWorkHookAlert,
    setConsensusProposal,
    setSendReceipt,
    setSendReceiptRaw,
  });

  const { handleVerifiedApprove, handleVerifiedReject, handleSynthesizeNow } =
    useRoomVerifiedHandlers({
      sessionId,
      showPlanApproval,
      verifiedEditGoal,
      verifiedEditCriteria,
      verifiedEditPromise,
      setVerifiedLoopBusy,
      setVerifiedLoopError,
      refreshSessionMeta,
      planExecute,
      executeSend,
      selected,
      synthesizing,
      running,
      runBusy,
      messages,
      onSessionChange,
      openPlanTab,
      clearRunWatchdog,
      setRecoveryFailure,
    });

  const {
    handleReleaseRunLock,
    handleRecoveryAction,
    handleRecoveryRetryAction,
  } = useRoomRecoveryActions({
    sessionId,
    activeSessionIdRef,
    lastPlainSendTextRef,
    slashCommands,
    onOpenSettings,
    onRefreshHealth,
    onSessionChange,
    refreshSessionMeta,
    setReadiness,
    setReleasingLock,
    setRunLockStuck,
    setRecoveryFailure,
    setDiscussRecoveryBusy,
    setRecoveryBusyAction,
    setText,
    setWorkFocus,
    beginRecoveryAttempt,
    finishRecoveryAction,
    executeSlashCommand,
    notifyRecoveryStarted,
    openWorkTab,
    openHumanInbox,
    openTranscriptTab,
  });

  function handleSend() {
    const msg = text.trim();
    if (msg.startsWith("/")) {
      const cmd = matchSlashCommand(msg, slashCommands);
      if (cmd) {
        void runSlashCommand(cmd, msg);
        return;
      }
    }
    if (
      (!msg && pendingFiles.length === 0) ||
      runBusy ||
      running ||
      synthesizing ||
      (loading && waitingForSession) ||
      selected.length === 0
    ) {
      return;
    }
    const missionAutonomous = Boolean(
      (
        session?.run?.mission_loop as
          | { autonomous_segment?: { active?: boolean } }
          | undefined
      )?.autonomous_segment?.active,
    );
    const needsPermissionPrompt =
      agentsNeedingPermissionPrompt(selected).length > 0 &&
      (!hasSavedPermissionDefaults() || missionAutonomous);
    if (needsPermissionPrompt) {
      setPendingSend({
        text: msg,
        files: pendingFiles,
        turnProfile,
      });
      setPermOpen(true);
      return;
    }
    void executeSend(msg, pendingFiles, roomPermissions(selected));
    setText("");
  }

  const focusObjection = useCallback(
    (_objectionId: string) => {
      focusWorkStack("plan_approval");
    },
    [focusWorkStack],
  );

  const handleInboxRefClick = useCallback(
    (ref: string) => {
      activateInboxRef(ref, {
        onChatLine: transcript.handlePlanRefClick,
        onOpenPlan: () => {
          openFilesTab();
          focusWorkStack("plan");
        },
        onFocusTask: transcript.focusTask,
      });
    },
    [
      transcript.focusTask,
      transcript.handlePlanRefClick,
      openFilesTab,
      focusWorkStack,
    ],
  );

  useEffect(() => {
    setComposerNoticeDismissed(null);
  }, [sessionId, recoverySignature, planWorkflow?.phase, inboxPendingCount]);

  const { modelPopoverNode, authPopover, authPickerPopover, choicePopover } =
    useRoomComposerPopovers({
      sessionId,
      authRun,
      setAuthRun,
      secretCommand,
      secretValue,
      setSecretValue,
      setSecretCommand,
      commandChoices,
      commandChoiceIndex,
      setCommandChoiceIndex,
      commandScopeChoices,
      setCommandScopeChoices,
      commandMultiChoices,
      setCommandMultiChoices,
      multiSelected,
      setMultiSelected,
      modelPopover,
      setModelPopover,
      setCommandChoices,
      setCommandHint,
      executeSlashCommand,
      handleAuthRunComplete,
      applySessionScopedModels,
    });

  const title = isNew ? "Session" : session?.topic || sessionId || "Session";
  const {
    view: autonomyView,
    loading: autonomyLoading,
    changing: autonomyChanging,
    setLevel: setAutonomyLevel,
  } = useAutonomySession({
    sessionId,
    sessionRun: session?.run as Record<string, unknown> | undefined,
    reloadKey: inboxReloadKey,
  });
  const titleMeta =
    !isNew || selected.length > 0
      ? `${selected.length} ${selected.length === 1 ? "agent" : "agents"}`
      : undefined;

  const planMeta = buildPlanMetaView(session?.run);
  const workPlanStaleNotice = tweaks.planStaleDemo
    ? DEMO_PLAN_STALE_NOTICE
    : composerPlanStale;
  const currentPlanRevision =
    planMeta.lastUpdate?.completed_at || planMeta.lastUpdate?.ts || null;

  const paletteActions = useRoomPaletteActions({
    slashCommands,
    setWorkspaceTab,
    running,
    handleStop,
    handleReleaseRunLock,
    onOpenSettings,
    openTranscriptTab,
    setText,
  });

  const composerClassName = useMemo(
    () =>
      [
        turnProfile === "review" ? "composer--review" : undefined,
        turnProfile === "loop" ? "composer--free" : undefined,
        composerModeVariant === "consensus"
          ? "composer--consensus-mode"
          : undefined,
        composerModeVariant === "plan" ? "composer--plan-mode" : undefined,
        composerModeVariant === "discuss"
          ? "composer--discuss-mode"
          : undefined,
      ]
        .filter(Boolean)
        .join(" ") || undefined,
    [turnProfile, composerModeVariant],
  );

  const composerEventStack = useRoomComposerEventStack({
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
    handlePlanRefClick: transcript.handlePlanRefClick,
    focusTask: transcript.focusTask,
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
    consensusGateDemo: tweaks.consensusGateDemo,
    setConsensusGateDemo: tweaks.setConsensusGateDemo,
    handleConsensusDryRun,
    dismissConsensusProposal,
    openDiffTab,
    openFilesTab,
    openFileInWorkbench,
    pushMacNotification,
  });

  return {
    paletteActions,
    title,
    titleMeta,
    autonomyView,
    autonomyLoading,
    autonomyChanging,
    setAutonomyLevel,
    inspectorOpen,
    rightPanelMode,
    locale,
    toggleInspector,
    handleSelectRightPanelMode,
    setWorkbenchMenuOpen,
    isNew,
    sessionId,
    avoidWorkbenchNotice,
    inboxPendingCount,
    inboxReloadKey,
    discussPaused,
    decisionRuntime,
    showPlanApproval,
    verifiedLoopPendingApproval: verifiedLoopView.pendingApproval,
    firstOpenBlock,
    consensusBlocked,
    planWorkflow,
    planWorkflowPlanIntent,
    showPlanWorkflowBanner,
    showPlanWorkflowComposerHint,
    recoveryVisible,
    recoveryLifecycleView,
    recoveryBusyActionId:
      recoveryBusyAction ??
      (releasingLock ? "release_lock" : null) ??
      (discussRecoveryBusy ? "run_discuss_recovery" : null),
    composerNoticeDismissed,
    setComposerNoticeDismissed,
    openHumanInbox,
    openWorkApproval,
    handleRecoveryAction,
    handleRecoveryRetryAction,
    setRecoveryDismissedSig,
    recoverySignature,
    transcript,
    runStartedAt,
    localeMsg,
    tweaks,
    handleNotificationOpen,
    composerEventStack,
    running,
    runBusy,
    readiness,
    healthAgents,
    selected,
    clarifierQuestions,
    clarifierInterview,
    planWorkflowActive,
    longRunning,
    handleStop,
    sendReceipt,
    sendReceiptRaw,
    composerClassName,
    text,
    setText,
    handleSend,
    slashCommands,
    runSlashCommand,
    composerInputLocked,
    composerSendLocked,
    composerPlaceholder,
    pendingFiles,
    addFiles,
    setPendingFiles,
    composerObjectionNotice,
    focusObjection,
    composerEmergenceHint,
    composerPresetHint,
    composerCostHint,
    visiblePresets,
    roomPreset,
    selectRoomPreset,
    agents,
    executeSlashCommand,
    commandHint,
    choicePopover,
    authPopover,
    authPickerPopover,
    modelPopoverNode,
    externalCommandConfirm,
    setExternalCommandConfirm,
    permOpen,
    setPermOpen,
    pendingSend,
    setPendingSend,
    executeSend,
    composeMode,
    loading,
    recoveryItemsLength: recoveryItems.length,
    goalView,
    planMeta,
    planExecutions,
    filesFocusPath,
    filesFocusRevision,
    workbenchPanelWidth,
    setActiveWorkbenchWidth,
    commitWorkbenchWidth,
    session,
    onOpenSettings,
    sidebarOpen,
    onToggleSidebar,
  };
}
