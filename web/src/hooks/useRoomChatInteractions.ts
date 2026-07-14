/** Workbench, send, recovery interactions (F9 P2). */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  cancelRoomRun,
  matchSlashCommand,
  pauseMissionLoop,
  steerSession,
} from "../api/client";
import { useWorkspaceTabs } from "./useWorkspaceTabs";
import { useRoomTranscriptView } from "./useRoomTranscriptView";
import {
  finalizeCancelledTyping,
  getRunningSessionIds,
  resolveRunSessionKey,
} from "../run/runSessionRegistry";
import {
  getLastRightPanelMode,
  setLastRightPanelMode,
} from "../utils/inspectorPanePrefs";
import { useRoomWorkbenchLayout } from "./useRoomWorkbenchLayout";
import {
  discussRecoveryFromMissionLoop,
  useRoomRecoveryLifecycle,
} from "./useRoomRecoveryLifecycle";
import type { PendingFile } from "../components/ChatComposer";
import {
  agentsNeedingPermissionPrompt,
  hasSavedPermissionDefaults,
  roomPermissions,
} from "../utils/agentPermissions";
import { dispatchNotification } from "../utils/pushNotification";
import { notifyDesktop } from "../utils/desktopNotify";
import { buildGoalLoopView } from "../utils/goalLoopView";
import { activateInboxRef } from "../utils/inboxRefNavigation";
import { focusComposerStack } from "../utils/composerStackFocus";
import { useRoomExecuteSend } from "./useRoomExecuteSend";
import { useRoomSlashExecute } from "./useRoomSlashExecute";
import { useRoomVerifiedHandlers } from "./useRoomVerifiedHandlers";
import {
  useRoomRecoveryActions,
  useRoomRecoveryNotifications,
} from "./useRoomRecoveryHandlers";
import { useRoomNotificationRouting } from "./useRoomNotificationRouting";
import type { useRoomChatBootstrap } from "./useRoomChatBootstrap";
import { useMissionReadModel } from "../utils/missionReadModel";

type Bootstrap = ReturnType<typeof useRoomChatBootstrap>;

export function useRoomChatInteractions(bootstrap: Bootstrap) {
  const { props } = bootstrap;
  const {
    sessionId,
    session,
    loading,
    onSessionMetaRefresh,
    onSessionChange,
    onOpenSettings,
    onRefreshHealth,
    bootstrapAgentThreadBindings,
    bootstrapSessionTemplate,
    onSessionBind,
    onBootstrapMissionTemplateApplied,
    apiOk = true,
    healthAgents = [],
    agents,
  } = props;
  const {
    openInspectorRef,
    openPlanApprovalWorkbenchRef,
    planShell,
    planMd,
    messages,
    running,
    runBusy,
    synthesizing,
    localSseRun,
    topologyActive,
    topologyDone,
    turnProfile,
    selected,
    text,
    pendingFiles,
    setText,
    setPendingFiles,
    setSelected,
    pushMacNotification,
    refreshSessionMeta,
    syncInboxPendingCount,
    refreshInboxPending,
    setDiscussPaused,
    planActionFocusIndex,
    setPlanActionFocusIndex,
    setGoalText,
    setGoalError,
    readiness,
    setReadiness,
    runLockStuck,
    setRunLockStuck,
    setReleasingLock,
    composerSendLocked,
    planExecutions,
    showPlanApproval,
    verifiedEditGoal,
    verifiedEditCriteria,
    verifiedEditPromise,
    setVerifiedLoopBusy,
    setVerifiedLoopError,
    roomTasks,
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
    runAbortRef,
    activeSessionIdRef,
    navigatedToSessionRef,
    pendingMissionTemplateRef,
    pendingSessionRoomModelsRef,
    agentsPickerInitRef,
    sendReceiptTimerRef,
    lastPlainSendTextRef,
    workspaceId,
    workspacePath,
    agentCapabilities,
    researchMode,
    roomPreset,
    composerModeVariant,
    locale,
    localeMsg,
    clearRunWatchdog,
    scheduleLongRunHint,
    clearLongRunHint,
    armStopWatchdog,
    notifyConsensusSync,
    notifyConsensusFailure,
    setInboxReloadKey,
    setClarifierQuestions,
    setClarifierInterview,
    setWorkHookAlert,
    setConsensusProposal,
    setSendReceipt,
    setSendReceiptRaw,
    setLiveRunSessionKey,
    setWorkFocus,
    planExecute,
    setPermOpen,
    setPendingSend,
    waitingForSession,
    isNew,
    setComposerNoticeDismissed,
    inboxPendingCount,
    persistPendingSessionRoomModels,
    planWorkflow,
  } = bootstrap;

  const [steerBusy, setSteerBusy] = useState(false);

  const openInspectorPane = useCallback(() => {
    openInspectorRef.current();
  }, [openInspectorRef]);

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

  const { model: missionReadModel } = useMissionReadModel(sessionId);

  const discussRecovery = useMemo(
    () => {
      if (
        missionReadModel?.state === "REPAIRING" ||
        missionReadModel?.state === "REPAIR"
      ) {
        return {
          pending: true,
          reason: missionReadModel.next_action,
          action_index: null,
        };
      }
      return discussRecoveryFromMissionLoop(session?.run?.mission_loop);
    },
    [missionReadModel, session?.run?.mission_loop],
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
    composerModeVariant,
    turnProfile,
    roomPreset,
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
      });
      setPermOpen(true);
      return;
    }
    void executeSend(msg, pendingFiles, roomPermissions(selected));
    setText("");
  }

  const steerEligible = Boolean(
    sessionId &&
    (running || runBusy) &&
    !planShell.planWorkflowAwaitingApproval,
  );

  const handleSteer = useCallback(() => {
    const msg = text.trim();
    if (!sessionId || !msg || steerBusy || !steerEligible) return;
    setSteerBusy(true);
    void steerSession(sessionId, msg)
      .then(() => {
        setText("");
      })
      .catch(() => {
        /* keep text for retry */
      })
      .finally(() => {
        setSteerBusy(false);
      });
  }, [sessionId, text, steerBusy, steerEligible, setText]);

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

  return {
    openInspectorPane,
    rightPanelMode,
    setWorkspaceTab,
    setRightPanelMode,
    openWorkTab,
    openPlanTab,
    openTranscriptTab,
    openDiffTab,
    openFilesTab,
    focusWorkStack,
    inspectorOpen,
    workbenchMenuOpen,
    setWorkbenchMenuOpen,
    filesFocusRevision,
    setFilesFocusRevision,
    filesFocusPath,
    setFilesFocusPath,
    workbenchPanelWidth,
    toggleInspector,
    setActiveWorkbenchWidth,
    commitWorkbenchWidth,
    handleSelectRightPanelMode,
    openHumanInbox,
    openWorkApproval,
    handleSteer,
    steerEligible,
    steerBusy,
    handleInboxBuildStarted,
    handleInboxResolved,
    handleNotificationOpen,
    transcript,
    goalView,
    openFileInWorkbench,
    avoidWorkbenchNotice,
    setRecoveryFailure,
    recoveryItems,
    recoveryLifecycleView,
    recoverySignature,
    recoveryVisible,
    setRecoveryDismissedSig,
    discussRecoveryBusy,
    recoveryBusyAction,
    addFiles,
    handleStop,
    applySessionScopedModels,
    executeSlashCommand,
    handleAuthRunComplete,
    runSlashCommand,
    executeSend,
    handleVerifiedApprove,
    handleVerifiedReject,
    handleSynthesizeNow,
    handleReleaseRunLock,
    handleRecoveryAction,
    handleRecoveryRetryAction,
    handleSend,
    focusObjection,
    handleInboxRefClick,
  };
}
