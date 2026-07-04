import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  AgentOption,
  PlanWorkflowRecord,
  SessionDetail,
} from "../api/client";
import {
  cancelRoomRun,
  postMissionDiscussRecovery,
  matchSlashCommand,
  releaseRoomRunLock,
  retryAgents,
  reconnectClaudeAuth,
  reconnectCursorBridge,
  reconnectKimiWorkBridge,
  runSynthesizeOnly,
  runRoomSlash,
  approveVerifiedLoop,
  approvePlan,
  rejectPlan,
  rejectVerifiedLoop,
  pauseMissionLoop,
  autoSyncSessionPlan,
  type AgentHealthRow,
} from "../api/client";
import { useInboxState } from "../hooks/useInboxState";
import { useGoalLoop } from "../hooks/useGoalLoop";
import { preferRicherChatMessages } from "../utils/sessionChatMerge";
import { syncSessionActivityMarkers } from "../utils/transcriptActivity";
import { isReplyWaitRole } from "../utils/transcript";
import { CommandPalette } from "./CommandPalette";
import { workspacePaletteActions } from "../utils/commandPaletteActions";
import { useWorkspaceTabs } from "../hooks/useWorkspaceTabs";
import { useSessionRunState } from "../hooks/useSessionRunState";
import {
  PENDING_KEY,
  clearBackgroundRun,
  finalizeCancelledTyping,
  getRunningSessionIds,
  getSessionRunSnapshot,
  hydrateSessionMessages,
  isSessionRunActive,
  markBackgroundRun,
  resolveRunSessionKey,
  syncRunStateFromLiveLog,
  updateSessionRun,
  type LiveMsg,
} from "../run/runSessionRegistry";
import { derivePendingReplyAgents } from "../run/runningAgents";
import { effectiveTurnAgents } from "../utils/agentMentions";
import { latestDraftMessageIdsByAgent } from "../utils/draftResponsePrefs";
import { stripAgentReplyBody } from "../utils/agentResponseCard";
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
import {
  getShowPeerChannel,
  setShowPeerChannel,
  TRANSCRIPT_VIEW_PREFS_EVENT,
} from "../utils/transcriptViewPrefs";
import { useHumanDecisionRuntime } from "../hooks/useHumanDecisionRuntime";
import { AutonomyDial } from "./AutonomyDial";
import type { PendingFile } from "./ChatComposer";
import type { PlanApprovalMode, PlanRejectPayload } from "./PlanApprovalPanel";
import { type WorkFocusTarget } from "./WorkToolPanel";
import { useMacNotifications } from "../hooks/useMacNotifications";
import type { AgentPermissions } from "../utils/agentPermissions";
import {
  agentsNeedingPermissionPrompt,
  hasSavedPermissionDefaults,
  roomPermissions,
} from "../utils/agentPermissions";
import {
  agreementPlanSyncFailedLabel,
  consensusDryRunNotifyBody,
  consensusDryRunNotifyTitle,
  latestPendingConsensusAgreement,
} from "../utils/consensusAgreement";
import { dispatchNotification } from "../utils/pushNotification";
import {
  notificationActionForKind,
  subscribeNotificationActions,
} from "../utils/notificationActions";
import type { AppNotification } from "../utils/notificationStore";
import { executionApprovalGate } from "../utils/executeApprovalGate";
import { notifyDesktop } from "../utils/desktopNotify";
import { buildPlanMetaView, composerPlanStaleNotice } from "../utils/planMeta";
import { buildGoalLoopView } from "../utils/goalLoopView";
import { activateInboxRef } from "../utils/inboxRefNavigation";
import { focusComposerStack } from "../utils/composerStackFocus";
import {
  isPlanWorkflowPhaseBanner,
  isPlanWorkflowComposerHint,
} from "../utils/planWorkflowView";
import {
  resolveTurnSend,
  type ComposerTurnProfile,
} from "../utils/turnProfile";
import { sortAgentIds } from "../utils/agentOrder";
import {
  readPendingRoomModels,
  readSessionRoomModels,
  writePendingRoomModels,
} from "../utils/modelSlash";
import type { ConsensusDryRunProposal } from "./ConsensusDryRunGateBar";
import { isPlanWorkflowAwaitingApproval } from "../utils/planComposerSync";
import { usePlanExecute } from "../hooks/usePlanExecute";
import { useLocale } from "../i18n/useLocale";
import {
  fetchSessionAgentCapabilities,
  fetchSessionTasks,
  type RoomObjection,
  type RoomTasksPayload,
} from "../api/client";
import {
  cloneCapabilities,
  DEFAULT_AGENT_CAPABILITIES,
  parseAgentCapabilities,
  type AgentCapabilitiesMap,
} from "../utils/agentCapabilities";
import {
  findChatLineIndexForTask,
  focusComposerInput,
  messageMentionsTask,
} from "../utils/taskBarCopy";
import { CUSTOM_WORKSPACE_ID } from "../utils/sessionSetup";
import { useRoomExecuteSend } from "../hooks/useRoomExecuteSend";
import { useRoomComposerPopovers } from "../hooks/useRoomComposerPopovers";
import { useRoomComposerEventStack } from "../hooks/useRoomComposerEventStack";
import { useRoomSlashExecute } from "../hooks/useRoomSlashExecute";
import { useRoomWorkspace } from "../hooks/useRoomWorkspace";
import { RoomChatMainPane } from "./RoomChatMainPane";
import { RoomChatInspector } from "./RoomChatInspector";
import {
  chatFingerprint,
  sessionToMessages,
} from "../utils/roomSessionMessages";
import { type AgentThreadBindings } from "../utils/agentThreadBindings";
import { fetchReadiness, type ReadinessResponse } from "../api/client";
import {
  type RecoveryActionId,
  type RecoveryItem,
} from "../utils/recoveryItems";
import {
  recoveryItemKey,
  type RecoveryResolutionEvent,
  type RecoveryRetryActionId,
} from "../utils/recoveryLifecycle";
import { useTweaksDemoOptional } from "../hooks/useTweaksDemo";
import { TWEAKS_DEMO_OFF } from "../context/tweaksDemoStore";
import {
  DEMO_CONSENSUS_PROPOSAL,
  DEMO_EXEC_PENDING,
  DEMO_EXEC_PENDING_BLOCKED,
  DEMO_OBJECTION_NOTICE,
  DEMO_PLAN_STALE_NOTICE,
} from "../utils/tweaksDemoFixtures";
import { useMessagesScroll } from "../hooks/useMessagesScroll";
import { WorkspaceChrome } from "./WorkspaceChrome";

type Props = {
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

export function RoomChat({
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
  sidebarOpen: _sidebarOpen,
  onToggleSidebar: _onToggleSidebar,
  onOpenSettings,
  onRefreshHealth,
  bootstrapAgentIds,
  bootstrapAgentThreadBindings,
  bootstrapSessionTemplate,
  bootstrapTopic,
  bootstrapMissionTemplateId,
  onBootstrapAgentsApplied,
  onBootstrapMissionTemplateApplied,
}: Props) {
  const { push: pushMacNotification } = useMacNotifications();
  const pendingMissionTemplateRef = useRef<string | null>(
    bootstrapMissionTemplateId ?? null,
  );
  useEffect(() => {
    if (bootstrapMissionTemplateId) {
      pendingMissionTemplateRef.current = bootstrapMissionTemplateId;
    }
  }, [bootstrapMissionTemplateId]);
  const pendingSessionRoomModelsRef = useRef<string[] | null>(null);
  const tweaks = useTweaksDemoOptional() ?? TWEAKS_DEMO_OFF;
  const [selected, setSelected] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  /** SSE start assigns a real session id before App props catch up. */
  const [liveRunSessionKey, setLiveRunSessionKey] = useState<string | null>(
    null,
  );
  const runSessionKey = sessionId ?? liveRunSessionKey ?? PENDING_KEY;
  const activeSessionIdRef = useRef<string | null>(sessionId);
  const {
    messages,
    running,
    runBusy,
    synthesizing,
    localSseRun,
    runStartedAt,
    topologyActive,
    topologyDone,
    setSynthesizing,
  } = useSessionRunState(runSessionKey);
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
  const [showPeerChannel, setShowPeerChannelState] =
    useState(getShowPeerChannel);
  const [workHookAlert, setWorkHookAlert] = useState<{
    event: string;
    body: string;
    blocked: boolean;
  } | null>(null);
  const [composerNoticeDismissed, setComposerNoticeDismissed] = useState<
    string | null
  >(null);
  const openInspectorRef = useRef<() => void>(() => {});
  const [roomTasks, setRoomTasks] = useState<RoomTasksPayload | null>(null);
  const [planMd, setPlanMd] = useState("");
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
    planComposeActive,
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
  const [highlightChatLine, setHighlightChatLine] = useState<number | null>(
    null,
  );
  const highlightTimerRef = useRef<number | null>(null);
  const [sendReceipt, setSendReceipt] = useState<string | null>(null);
  const [sendReceiptRaw, setSendReceiptRaw] = useState<string | undefined>();
  const [hideApprovedPlanBanner, setHideApprovedPlanBanner] = useState(false);
  const [discussPaused, setDiscussPaused] = useState(false);
  const [workFocus, setWorkFocus] = useState<WorkFocusTarget | null>(null);
  const prevExecPendingIdRef = useRef<string | null>(null);
  const sendReceiptTimerRef = useRef<number | null>(null);
  const [clarifierQuestions, setClarifierQuestions] = useState<string[] | null>(
    null,
  );
  const [clarifierInterview, setClarifierInterview] = useState<{
    questions?: { id?: string; category?: string; prompt?: string }[];
    plan_mode?: boolean;
  } | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
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
  const runAbortRef = useRef<AbortController | null>(null);
  const syncedChatRef = useRef("");
  const { workspaceId, workspacePath } = useRoomWorkspace(sessionId);
  const [consensusProposal, setConsensusProposal] =
    useState<ConsensusDryRunProposal | null>(null);
  const [consensusGateBusy, setConsensusGateBusy] = useState(false);
  const [agentCapabilities, setAgentCapabilities] =
    useState<AgentCapabilitiesMap>(() =>
      cloneCapabilities(DEFAULT_AGENT_CAPABILITIES),
    );
  const [, setResolvedAgentCwd] = useState<Record<string, string>>({});
  const navigatedToSessionRef = useRef(false);
  const agentCapsDirtyRef = useRef(false);
  const agentsPickerInitRef = useRef(false);

  useEffect(() => {
    activeSessionIdRef.current = sessionId;
    if (sessionId !== null) {
      setLiveRunSessionKey(null);
    }
  }, [sessionId]);

  useEffect(() => {
    const onPrefs = () => {
      setShowPeerChannelState(getShowPeerChannel());
    };
    window.addEventListener(TRANSCRIPT_VIEW_PREFS_EVENT, onPrefs);
    return () =>
      window.removeEventListener(TRANSCRIPT_VIEW_PREFS_EVENT, onPrefs);
  }, []);

  useEffect(() => {
    if (!sessionId) {
      setReadiness(null);
      return;
    }
    if (running || runBusy || synthesizing) {
      return;
    }
    let cancelled = false;
    void fetchReadiness(sessionId, true)
      .then((payload) => {
        if (!cancelled) setReadiness(payload);
      })
      .catch(() => {
        if (!cancelled) setReadiness(null);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, selected.join(","), running, runBusy, synthesizing]);

  useEffect(() => {
    if (sessionId !== null) return;
    setAgentCapabilities(cloneCapabilities(DEFAULT_AGENT_CAPABILITIES));
    setResolvedAgentCwd({});
    agentCapsDirtyRef.current = false;
    if (!agentsPickerInitRef.current) {
      const restored = readPendingRoomModels();
      if (restored?.length) {
        pendingSessionRoomModelsRef.current = restored;
        setSelected(restored);
        agentsPickerInitRef.current = true;
      }
    }
  }, [sessionId]);

  const sessionRoomModelsKey = useMemo(() => {
    const models = readSessionRoomModels(
      session?.run as Record<string, unknown> | undefined,
    );
    return models ? models.join(",") : null;
  }, [session?.run]);

  useEffect(() => {
    if (!sessionId || !sessionRoomModelsKey) return;
    const models = readSessionRoomModels(
      session?.run as Record<string, unknown> | undefined,
    );
    if (!models) return;
    setSelected((prev) => {
      const next = sortAgentIds(models);
      return prev.join(",") === next.join(",") ? prev : next;
    });
    agentsPickerInitRef.current = true;
  }, [session?.run, sessionId, sessionRoomModelsKey]);

  const persistPendingSessionRoomModels = useCallback(
    async (boundSessionId: string) => {
      const pending = pendingSessionRoomModelsRef.current;
      if (!pending?.length) return;
      pendingSessionRoomModelsRef.current = null;
      writePendingRoomModels(null);
      try {
        await runRoomSlash(
          `/model ${pending.join(",")} session`,
          boundSessionId,
        );
      } catch {
        pendingSessionRoomModelsRef.current = pending;
        writePendingRoomModels(pending);
      }
    },
    [],
  );

  useEffect(() => {
    if (!sessionId) {
      setResolvedAgentCwd({});
      return;
    }
    if (agentCapsDirtyRef.current) {
      const perms = roomPermissions(selected);
      void fetchSessionAgentCapabilities(
        sessionId,
        perms as Record<string, unknown>,
      )
        .then((r) => setResolvedAgentCwd(r.resolved_cwd ?? {}))
        .catch(() => {});
      return;
    }
    const raw = session?.run?.agent_capabilities;
    if (raw && typeof raw === "object") {
      setAgentCapabilities(parseAgentCapabilities(raw));
    }
    const perms = roomPermissions(selected);
    void fetchSessionAgentCapabilities(
      sessionId,
      perms as Record<string, unknown>,
    )
      .then((r) => {
        if (!raw && r.agent_capabilities) {
          setAgentCapabilities(parseAgentCapabilities(r.agent_capabilities));
        }
        setResolvedAgentCwd(r.resolved_cwd ?? {});
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    sessionId,
    selected.join(","),
    JSON.stringify(session?.run?.agent_capabilities),
  ]);

  function effectiveSessionId(): string | null {
    return sessionId ?? activeSessionIdRef.current;
  }

  const refreshTasks = useCallback(
    (overrideId?: string | null) => {
      const sid = overrideId ?? sessionId ?? activeSessionIdRef.current;
      if (!sid) {
        setRoomTasks(null);
        return;
      }
      void fetchSessionTasks(sid)
        .then(setRoomTasks)
        .catch(() => setRoomTasks(null));
    },
    [sessionId],
  );

  const refreshSessionMeta = useCallback(() => {
    const sid = effectiveSessionId();
    if (!sid) return;
    if (onSessionMetaRefresh) {
      void onSessionMetaRefresh(sid);
    } else {
      void onSessionChange(sid);
    }
    refreshTasks(sid);
    refreshCommands(sid);
  }, [onSessionMetaRefresh, onSessionChange, refreshTasks, refreshCommands]);

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

  useEffect(() => {
    refreshTasks();
  }, [
    refreshTasks,
    (session?.run?.artifacts as unknown[] | undefined)?.length,
    session?.run?.status,
    session?.chat?.length,
  ]);

  const planExecute = usePlanExecute({
    sessionId,
    run: session?.run,
    onUpdated: refreshSessionMeta,
  });

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
      hasPendingExecution,
      hasDryRunDiff,
      planMd,
      hasBlocker,
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

  const handleNotificationOpen = useCallback(
    (note: AppNotification) => {
      const action = notificationActionForKind(note.kind);
      if (!action) return;
      if (action.type === "composer") {
        focusComposerStack(action.focus ?? "inbox");
        return;
      }
      if (action.type === "work") {
        focusWorkStack(action.focus === "execute" ? "execute" : "plan");
        return;
      }
      if (action.type === "inspector") {
        setRightPanelMode("overview");
        return;
      }
      if (action.type === "settings") {
        onOpenSettings?.();
        return;
      }
    },
    [focusWorkStack, onOpenSettings, setRightPanelMode],
  );

  useEffect(() => {
    return subscribeNotificationActions((action) => {
      if (action.type === "composer") {
        focusComposerStack(action.focus ?? "inbox");
        return;
      }
      if (action.type === "work") {
        focusWorkStack(action.focus === "execute" ? "execute" : "plan");
        return;
      }
      if (action.type === "inspector") {
        setRightPanelMode("overview");
        return;
      }
      if (action.type === "settings") {
        onOpenSettings?.();
        return;
      }
    });
  }, [focusWorkStack, onOpenSettings, setRightPanelMode]);

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

  const visibleMessages = useMemo(() => {
    const rows = messages.filter((m) => !m.humanSynthesis);
    if (showPeerChannel) return rows;
    return rows.filter((m) => !m.peerChannel);
  }, [messages, showPeerChannel]);

  const openDraftMessageIds = useMemo(
    () =>
      latestDraftMessageIdsByAgent(
        visibleMessages,
        (role) => isReplyWaitRole(role as LiveMsg["role"]),
        (body) => Boolean(stripAgentReplyBody(body ?? "").trim()),
      ),
    [visibleMessages],
  );

  // S1 Phase D: advisor rationale per completed turn (0-based, mirrors run.turns order)
  const advisorRationales = useMemo(() => {
    const turns = session?.run?.turns;
    if (!Array.isArray(turns)) return [] as (string | null)[];
    return (turns as Array<Record<string, unknown>>).map((t) => {
      const tm = t?.turn_metrics;
      if (!tm || typeof tm !== "object") return null;
      const rat = (tm as Record<string, unknown>).advisor_rationale;
      return typeof rat === "string" && rat ? rat : null;
    });
  }, [session?.run?.turns]);

  const transcriptActive = true;
  const typingAgents = messages.filter(
    (m) => m.typing && isReplyWaitRole(m.role),
  );
  const pendingReplyCount =
    running && typingAgents.length === 0
      ? resolveTurnSend(turnProfile, selected).agents.length
      : 0;
  const { scrollRef, scrollElRef, showJumpButton, scrollToBottom } =
    useMessagesScroll(
      [messages, running, pendingReplyCount, selected.join(",")],
      transcriptActive,
      `${sessionId ?? "new"}:chat`,
    );

  const planExecutions = planExecute.executions;

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

  const isNew = !sessionId;

  useEffect(() => {
    setGoalText(buildGoalLoopView(session?.run).goal.text ?? "");
    setGoalError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, JSON.stringify(session?.run?.session_goal)]);

  const goalView = useMemo(
    () => buildGoalLoopView(session?.run),
    [session?.run],
  );

  const planWorkflow = session?.run?.plan_workflow as
    | PlanWorkflowRecord
    | undefined;
  const planWorkflowPlanIntent =
    typeof session?.run?.plan_intent === "string"
      ? session.run.plan_intent
      : null;
  const planWorkflowActive = Boolean(planWorkflow?.enabled);
  const showPlanApproval =
    planWorkflowActive &&
    (planWorkflow?.phase === "HUMAN_PENDING" ||
      verifiedLoopView.pendingApproval);

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
    typeof session?.run?.active_plan_relpath === "string" &&
    session.run.active_plan_relpath.trim()
      ? session.run.active_plan_relpath.trim()
      : "plan.md";

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

  useEffect(() => {
    if (!showPlanApproval || !sessionId) return;
    setFilesFocusPath(activePlanRelpath);
    setFilesFocusRevision((n) => n + 1);
    openFilesTab();
  }, [showPlanApproval, sessionId, planMd, openFilesTab, activePlanRelpath]);

  const avoidWorkbenchNotice = inspectorOpen || workbenchMenuOpen;

  const waitingForSession = Boolean(sessionId && !session && loading);
  const composerInputLocked = waitingForSession;
  const preflightBlocked = selected.some((id) => {
    const row = healthAgents.find((a) => a.id === id);
    return Boolean(row && !row.ready);
  });
  const customWorkspaceBlocked =
    isNew && workspaceId === CUSTOM_WORKSPACE_ID && !workspacePath?.trim();
  const planWorkflowAwaitingApproval =
    isPlanWorkflowAwaitingApproval(planWorkflow);
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

  const notifyRecoveryResolution = useCallback(
    (event: RecoveryResolutionEvent) => {
      const workRecovery =
        event.kind === "oracle_fail" || event.kind === "discuss_recovery";
      dispatchNotification(
        {
          tier: event.status === "resolved" ? "P1" : "P0",
          title:
            event.status === "resolved"
              ? "Recovery resolved"
              : "Recovery still blocked",
          body: event.message,
          sessionId: sessionId ?? undefined,
          kind:
            event.status === "resolved"
              ? workRecovery
                ? "recovery_resolved_work"
                : "recovery_resolved"
              : "recovery_still_blocked",
          entityId: event.key,
          toastAction:
            event.status === "resolved" && workRecovery
              ? { type: "composer", focus: "execute" }
              : undefined,
        },
        pushMacNotification,
        notifyDesktop,
      );
    },
    [pushMacNotification, sessionId],
  );

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
    executeError: planExecute.error,
    planExecutions: planExecutions,
    composerSendLocked,
    onResolutionNotify: notifyRecoveryResolution,
  });

  const handleReleaseRunLock = useCallback(async () => {
    setReleasingLock(true);
    try {
      await releaseRoomRunLock();
      setRunLockStuck(false);
      setRecoveryFailure(null);
    } catch (e) {
      setRecoveryFailure({ source: "command", message: String(e) });
    } finally {
      setReleasingLock(false);
    }
  }, [setRecoveryFailure, setReleasingLock, setRunLockStuck]);

  const handleRetryFailedAgents = useCallback(async () => {
    const sid = sessionId ?? activeSessionIdRef.current;
    if (!sid) return;
    markBackgroundRun(sid, {
      runKind: "retry",
      label: "Retry failed agents",
    });
    try {
      await retryAgents(sid);
      await onSessionChange(sid);
      setRecoveryFailure(null);
    } finally {
      clearBackgroundRun(sid, "retry");
    }
  }, [onSessionChange, sessionId, setRecoveryFailure]);

  const sessionReviewMode = Boolean(
    (session?.run?.last_turn as { review_mode?: boolean } | undefined)
      ?.review_mode,
  );

  useEffect(() => {
    const rosterPool =
      teamHealthAgents.length > 0
        ? teamHealthAgents
        : healthAgents.length > 0
          ? healthAgents
          : agents;
    const ready = rosterPool.filter((a) => a.ready).map((a) => a.id);
    const known = new Set([
      ...rosterPool.map((a) => a.id),
      ...agents.map((a) => a.id),
    ]);
    if (ready.length === 0 && known.size === 0) return;
    setSelected((prev) => {
      const pending = pendingSessionRoomModelsRef.current;
      if (pending?.length) {
        const next = sortAgentIds(pending);
        return prev.join(",") === next.join(",") ? prev : next;
      }
      if (bootstrapAgentIds?.length) {
        const picked = sortAgentIds(bootstrapAgentIds);
        if (picked.length > 0) return picked;
      }
      if (!agentsPickerInitRef.current || prev.length === 0) {
        agentsPickerInitRef.current = true;
        if (ready.length > 0) return sortAgentIds(ready);
        return prev;
      }
      // Keep explicit user picks when health flips ready=false; only drop unknown ids.
      const kept = sortAgentIds(prev.filter((id) => known.has(id)));
      if (kept.length > 0) return kept;
      if (ready.length > 0) return sortAgentIds(ready);
      return prev;
    });
  }, [agents, bootstrapAgentIds, healthAgents, teamHealthAgents]);

  useEffect(() => {
    if (!sessionId && bootstrapAgentIds?.length) {
      onBootstrapAgentsApplied?.();
    }
  }, [sessionId, bootstrapAgentIds, onBootstrapAgentsApplied]);

  useEffect(() => {
    if (sessionId || !bootstrapTopic?.trim()) return;
    setText((prev) => (prev.trim() ? prev : bootstrapTopic));
  }, [sessionId, bootstrapTopic]);

  const prevSessionIdRef = useRef<string | null>(sessionId);

  useEffect(() => {
    const prev = prevSessionIdRef.current;
    prevSessionIdRef.current = sessionId;

    if (prev === sessionId) return;

    if (sessionId === null) {
      setSynthesizing(false);
      return;
    }

    if (prev !== null && prev !== sessionId) {
      agentCapsDirtyRef.current = false;
      syncedChatRef.current = "";
      setPlanMd("");
    }
  }, [sessionId, setSynthesizing]);

  useEffect(() => {
    if (sessionId !== null) return;
    setSynthesizing(false);
    setText("");
    setPendingFiles([]);
  }, [sessionId, setSynthesizing]);

  useEffect(() => {
    syncedChatRef.current = "";
  }, [sessionId]);

  useEffect(() => {
    setConsensusProposal(null);
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId || !session) return;
    const local = getSessionRunSnapshot(sessionId);
    const runActive = isSessionRunActive(sessionId);
    if (runActive && local.messages.length > 0) return;

    const fp = chatFingerprint(session);
    if (fp !== syncedChatRef.current) {
      const serverMsgs = sessionToMessages(session, sessionReviewMode);
      const merged = preferRicherChatMessages(local.messages, serverMsgs);
      syncedChatRef.current = fp;
      hydrateSessionMessages(sessionId, merged);
      syncRunStateFromLiveLog(sessionId, session.live_log);
      syncSessionActivityMarkers(sessionId);
    }
    setPlanMd(session.plan_md || "");
  }, [session, sessionId, sessionReviewMode]);

  useEffect(() => {
    if (!sessionId) return;
    syncSessionActivityMarkers(sessionId);
  }, [sessionId]);

  useEffect(() => {
    if (sessionId !== null) return;
    syncedChatRef.current = "";
    setLiveRunSessionKey(null);
    navigatedToSessionRef.current = false;
    if (!isSessionRunActive(PENDING_KEY)) {
      hydrateSessionMessages(PENDING_KEY, []);
    }
    setPlanMd("");
  }, [sessionId]);

  function addFiles(fileList: FileList | File[]) {
    const next: PendingFile[] = [];
    for (const f of Array.from(fileList)) {
      next.push({ id: `${f.name}-${f.size}-${Date.now()}`, file: f });
    }
    setPendingFiles((prev) => [...prev, ...next]);
  }

  const handlePlanRefClick = useCallback(
    (lineNumber: number) => {
      openTranscriptTab();
      setHighlightChatLine(lineNumber - 1);
    },
    [openTranscriptTab],
  );

  useEffect(() => {
    if (highlightChatLine == null) return;
    const root = scrollElRef.current;
    const el = root?.querySelector(
      `[data-chat-line="${highlightChatLine}"]`,
    ) as HTMLElement | null;
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    if (highlightTimerRef.current != null) {
      window.clearTimeout(highlightTimerRef.current);
    }
    highlightTimerRef.current = window.setTimeout(() => {
      setHighlightChatLine(null);
      highlightTimerRef.current = null;
    }, 2600);
    return () => {
      if (highlightTimerRef.current != null) {
        window.clearTimeout(highlightTimerRef.current);
      }
    };
  }, [highlightChatLine, messages, scrollElRef]);

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

  function notifyConsensusSync(proposal: ConsensusDryRunProposal) {
    const title = consensusDryRunNotifyTitle(proposal.excerpt);
    const body = consensusDryRunNotifyBody(
      proposal.summary,
      proposal.recommended?.what,
    );
    const freeConsensus = turnProfile === "loop";
    dispatchNotification(
      {
        tier: "P1",
        title,
        body,
        sessionId: sessionId ?? undefined,
        kind: proposal.recommended ? "consensus_complete" : "plan_sync",
        entityId: proposal.action_key ?? proposal.excerpt,
        toastAction: freeConsensus
          ? { type: "composer", focus: "plan" }
          : undefined,
      },
      pushMacNotification,
      notifyDesktop,
    );
  }

  function notifyConsensusFailure(excerpt?: string, message?: string) {
    const title = agreementPlanSyncFailedLabel(excerpt, message);
    dispatchNotification(
      {
        tier: "P0",
        title,
        sessionId: sessionId ?? undefined,
        kind: "plan_sync_fail",
        entityId: excerpt,
      },
      pushMacNotification,
      notifyDesktop,
    );
  }

  const notifyRecoveryStarted = useCallback(
    (item: RecoveryItem, actionId: RecoveryActionId) => {
      dispatchNotification(
        {
          tier: "P2",
          title: "Recovery action started",
          body: `${item.title} · ${actionId}`,
          sessionId: sessionId ?? undefined,
          kind: "recovery_started",
          entityId: recoveryItemKey(item),
        },
        pushMacNotification,
        notifyDesktop,
      );
    },
    [pushMacNotification, sessionId],
  );

  const handleConsensusDryRun = useCallback(async () => {
    const key = consensusProposal?.action_key;
    if (!key) return;
    setConsensusGateBusy(true);
    try {
      planExecute.setSelectedKey(key);
      await planExecute.refreshActions();
      const ok = await planExecute.dryRun(key);
      if (ok) setConsensusProposal(null);
    } finally {
      setConsensusGateBusy(false);
    }
  }, [consensusProposal, planExecute]);

  const dismissConsensusProposal = useCallback(() => {
    setConsensusProposal(null);
  }, []);

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
    planComposeActive,
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

  const handleVerifiedApprove = useCallback(
    async (mode: PlanApprovalMode = "approve_only") => {
      if (!sessionId || (!showPlanApproval && !verifiedEditGoal.trim())) return;
      setVerifiedLoopBusy(true);
      setVerifiedLoopError(null);
      try {
        const res = showPlanApproval
          ? await approvePlan(sessionId)
          : await approveVerifiedLoop(sessionId, {
              goal: verifiedEditGoal.trim(),
              completion_promise: verifiedEditPromise.trim() || "DONE",
              criteria: verifiedEditCriteria.trim() || verifiedEditGoal.trim(),
            });
        await refreshSessionMeta();
        if (showPlanApproval && mode === "execute") {
          await planExecute.dryRun();
        }
        const prompt =
          "continue_prompt" in res
            ? (res.continue_prompt as string | undefined)?.trim()
            : undefined;
        if (prompt && !showPlanApproval) {
          void executeSend(
            prompt,
            [],
            roomPermissions(selected),
            "discuss",
            "verified",
          );
        }
      } catch (e) {
        setVerifiedLoopError(String(e));
      } finally {
        setVerifiedLoopBusy(false);
      }
    },
    [
      sessionId,
      verifiedEditGoal,
      verifiedEditCriteria,
      verifiedEditPromise,
      refreshSessionMeta,
      executeSend,
      selected,
      showPlanApproval,
      planExecute,
    ],
  );

  const handleVerifiedReject = useCallback(
    async (payload?: PlanRejectPayload) => {
      if (!sessionId) return;
      setVerifiedLoopBusy(true);
      setVerifiedLoopError(null);
      try {
        if (showPlanApproval) {
          await rejectPlan(sessionId, {
            note: payload?.note ?? "Human requested plan revise",
            target_phase: payload?.target_phase ?? "CLARIFY",
          });
        } else {
          await rejectVerifiedLoop(sessionId);
        }
        await refreshSessionMeta();
      } catch (e) {
        setVerifiedLoopError(String(e));
      } finally {
        setVerifiedLoopBusy(false);
      }
    },
    [sessionId, refreshSessionMeta, showPlanApproval],
  );

  const executeSynthesizeOnly = useCallback(
    async (permissions: AgentPermissions) => {
      if (!sessionId || synthesizing) return;
      const requestId = crypto.randomUUID();
      updateSessionRun(sessionId, {
        synthesizing: true,
        runBusy: true,
        running: true,
      });
      setRecoveryFailure(null);
      try {
        await runSynthesizeOnly(
          sessionId,
          (ev) => {
            if (String(ev.type) === "error") {
              setRecoveryFailure({
                source: "run",
                message: String(ev.message ?? "plan synthesis failed"),
              });
            }
          },
          { requestId, permissions },
        );
        openPlanTab();
        await onSessionChange(sessionId);
      } catch (e) {
        setRecoveryFailure({ source: "transport", message: String(e) });
      } finally {
        clearRunWatchdog();
        updateSessionRun(sessionId, {
          synthesizing: false,
          runBusy: false,
          running: false,
        });
      }
    },
    [sessionId, synthesizing, onSessionChange, openPlanTab],
  );

  function handleSynthesizeNow() {
    if (
      running ||
      runBusy ||
      synthesizing ||
      !sessionId ||
      messages.length === 0
    )
      return;
    void executeSynthesizeOnly(roomPermissions(selected));
  }

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
  const focusTask = useCallback(
    (taskId: string) => {
      openTranscriptTab();
      focusWorkStack("plan");
      const task =
        roomTasks?.tasks?.find((t) => t.id === taskId) ??
        roomTasks?.claimable?.find((t) => t.id === taskId);
      const chatLines = session?.chat ?? [];
      let lineIdx: number | null = null;
      if (task) {
        lineIdx = findChatLineIndexForTask(chatLines, task);
      }
      if (lineIdx == null && task) {
        for (let i = messages.length - 1; i >= 0; i -= 1) {
          const m = messages[i];
          if (m.chatLineIndex == null) continue;
          if (messageMentionsTask(m.body ?? "", task)) {
            lineIdx = m.chatLineIndex;
            break;
          }
        }
      }
      if (lineIdx != null) {
        setHighlightChatLine(lineIdx);
      }
      window.setTimeout(() => {
        document
          .querySelector(`[data-task-id="${taskId}"]`)
          ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 60);
    },
    [roomTasks, session?.chat, messages, openTranscriptTab, focusWorkStack],
  );

  const handleInboxRefClick = useCallback(
    (ref: string) => {
      activateInboxRef(ref, {
        onChatLine: handlePlanRefClick,
        onOpenPlan: () => {
          openFilesTab();
          focusWorkStack("plan");
        },
        onFocusTask: focusTask,
      });
    },
    [focusTask, handlePlanRefClick, openFilesTab, focusWorkStack],
  );

  const handleDiscussRecoveryRun = useCallback(async () => {
    if (!sessionId) return;
    setDiscussRecoveryBusy(true);
    try {
      await postMissionDiscussRecovery(sessionId);
      refreshSessionMeta();
    } finally {
      setDiscussRecoveryBusy(false);
    }
  }, [refreshSessionMeta, sessionId]);

  const refreshRecoveryReadiness = useCallback(async () => {
    await onRefreshHealth?.();
    if (sessionId) {
      const next = await fetchReadiness(sessionId, true);
      setReadiness(next);
    }
    refreshSessionMeta();
  }, [onRefreshHealth, refreshSessionMeta, sessionId]);

  const handleRecoveryAction = useCallback(
    async (actionId: RecoveryActionId, item: RecoveryItem) => {
      const tracksResolution =
        actionId !== "open_settings" &&
        actionId !== "open_work" &&
        actionId !== "open_inbox";
      let attemptId: string | null = null;
      if (tracksResolution) {
        attemptId = beginRecoveryAttempt(
          item,
          actionId,
          Boolean(lastPlainSendTextRef.current),
        );
        notifyRecoveryStarted(item, actionId);
      }
      setRecoveryBusyAction(actionId);
      try {
        switch (actionId) {
          case "open_settings":
            onOpenSettings?.();
            return;
          case "refresh_health":
            await refreshRecoveryReadiness();
            return;
          case "reconnect_cursor":
            await reconnectCursorBridge();
            await refreshRecoveryReadiness();
            return;
          case "reconnect_claude": {
            const loginCmd = slashCommands.find(
              (candidate) => candidate.id === "login",
            );
            if (loginCmd) {
              await executeSlashCommand(loginCmd, "claude");
              return;
            }
            await reconnectClaudeAuth();
            await refreshRecoveryReadiness();
            return;
          }
          case "reconnect_codex": {
            const loginCmd = slashCommands.find(
              (candidate) => candidate.id === "login",
            );
            if (loginCmd) {
              await executeSlashCommand(loginCmd, "codex");
              return;
            }
            onOpenSettings?.();
            return;
          }
          case "reconnect_kimi_work":
            await reconnectKimiWorkBridge();
            await refreshRecoveryReadiness();
            return;
          case "release_lock":
            await handleReleaseRunLock();
            return;
          case "retry_failed_agents":
            await handleRetryFailedAgents();
            return;
          case "open_work":
            openWorkTab();
            setWorkFocus("execute");
            return;
          case "open_inbox":
            openHumanInbox();
            return;
          case "run_discuss_recovery":
            await handleDiscussRecoveryRun();
            return;
        }
      } catch (e) {
        setRecoveryFailure({
          source: "command",
          message: e instanceof Error ? e.message : String(e),
        });
      } finally {
        finishRecoveryAction(attemptId);
      }
    },
    [
      beginRecoveryAttempt,
      executeSlashCommand,
      finishRecoveryAction,
      handleDiscussRecoveryRun,
      handleReleaseRunLock,
      handleRetryFailedAgents,
      notifyRecoveryStarted,
      onOpenSettings,
      openHumanInbox,
      openWorkTab,
      refreshRecoveryReadiness,
      setRecoveryBusyAction,
      setRecoveryFailure,
      slashCommands,
    ],
  );

  const handleRecoveryRetryAction = useCallback(
    (actionId: RecoveryRetryActionId, event: RecoveryResolutionEvent): void => {
      if (event.kind === "oracle_fail" || event.kind === "discuss_recovery") {
        openWorkTab();
        setWorkFocus("execute");
        return;
      }
      openTranscriptTab();
      if (actionId === "restore_last_message" && lastPlainSendTextRef.current) {
        setText(lastPlainSendTextRef.current);
      }
      focusComposerInput();
    },
    [openTranscriptTab, openWorkTab],
  );
  const executeBusy = planExecute.busy;

  useEffect(() => {
    setComposerNoticeDismissed(null);
  }, [sessionId, recoverySignature, planWorkflow?.phase, inboxPendingCount]);

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
  const composerPlanStale = composerPlanStaleNotice(session?.run);
  const planAutoSyncKey = composerPlanStale
    ? `${sessionId ?? ""}:${composerPlanStale}`
    : null;
  const planAutoSyncRef = useRef<string | null>(null);
  useEffect(() => {
    if (!sessionId || !planAutoSyncKey || running || synthesizing || runBusy) {
      return;
    }
    if (planAutoSyncRef.current === planAutoSyncKey) return;
    planAutoSyncRef.current = planAutoSyncKey;
    void autoSyncSessionPlan(sessionId)
      .then((detail) => {
        const pending = latestPendingConsensusAgreement(detail.run);
        if (pending?.excerpt) {
          notifyConsensusFailure(
            pending.excerpt,
            "plan.md 자동 정리에 실패했습니다",
          );
          planAutoSyncRef.current = null;
          return;
        }
        refreshSessionMeta();
        setInboxReloadKey((k) => k + 1);
      })
      .catch(() => {
        notifyConsensusFailure(undefined, "plan.md 자동 정리 요청 실패");
        planAutoSyncRef.current = null;
      });
  }, [
    sessionId,
    planAutoSyncKey,
    running,
    synthesizing,
    runBusy,
    refreshSessionMeta,
  ]);
  const workPlanStaleNotice = tweaks.planStaleDemo
    ? DEMO_PLAN_STALE_NOTICE
    : composerPlanStale;
  const currentPlanRevision =
    planMeta.lastUpdate?.completed_at || planMeta.lastUpdate?.ts || null;
  const turnResolved = resolveTurnSend(turnProfile, selected);
  const turnUserBody = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const row = messages[i];
      if (row?.role === "you" && row.sent) return row.body ?? "";
    }
    return "";
  }, [messages]);
  const turnTargetAgents = useMemo(
    () => effectiveTurnAgents(turnUserBody, turnResolved.agents),
    [turnUserBody, turnResolved.agents],
  );
  const pendingReplyAgents = useMemo(
    () =>
      derivePendingReplyAgents(messages, {
        running: running || localSseRun,
        expectedAgents: turnTargetAgents,
        topologyActive,
        topologyDone,
      }),
    [
      messages,
      running,
      localSseRun,
      turnTargetAgents,
      topologyActive,
      topologyDone,
    ],
  );

  const paletteActions = useMemo(() => {
    const commandActions = slashCommands
      .filter((cmd) => cmd.enabled !== false)
      .map((cmd) => ({
        id: `slash-${cmd.id}`,
        label: `Insert ${cmd.slash}`,
        hint: `${cmd.agent ?? cmd.kind}${
          cmd.description ? ` · ${cmd.description}` : ""
        }`,
        run: () => {
          openTranscriptTab();
          setText(`${cmd.slash} `);
          window.setTimeout(() => focusComposerInput(), 0);
        },
      }));
    return workspacePaletteActions(setWorkspaceTab, [
      {
        id: "stop-run",
        label: running ? "Stop run" : "Stop run",
        hint: running ? "⌘." : undefined,
        run: () => {
          if (running) handleStop();
        },
      },
      {
        id: "release-lock",
        label: "Release run lock",
        run: () => void handleReleaseRunLock(),
      },
      {
        id: "open-plugins",
        label: "Open settings",
        hint: "Agents · Workspace · Commands",
        run: () => {
          onOpenSettings?.();
        },
      },
      {
        id: "focus-composer",
        label: "Focus composer",
        run: () => focusComposerInput(),
      },
      ...commandActions,
    ]);
  }, [
    setWorkspaceTab,
    running,
    handleStop,
    handleReleaseRunLock,
    onOpenSettings,
    slashCommands,
    openTranscriptTab,
    focusComposerInput,
  ]);

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
    consensusGateDemo: tweaks.consensusGateDemo,
    setConsensusGateDemo: tweaks.setConsensusGateDemo,
    handleConsensusDryRun,
    dismissConsensusProposal,
    openDiffTab,
    openFilesTab,
    openFileInWorkbench,
    pushMacNotification,
  });

  return (
    <>
      <CommandPalette actions={paletteActions} />

      <WorkspaceChrome
        title={title}
        meta={titleMeta}
        headerExtra={
          sessionId ? (
            <AutonomyDial
              view={autonomyView}
              loading={autonomyLoading}
              changing={autonomyChanging}
              disabled={running || runBusy}
              onLevelChange={setAutonomyLevel}
            />
          ) : null
        }
        sidebarOpen={_sidebarOpen}
        rightPanelOpen={inspectorOpen}
        rightPanelMode={rightPanelMode}
        locale={locale}
        onToggleSidebar={_onToggleSidebar}
        onToggleRightPanel={toggleInspector}
        onSelectRightPanelMode={handleSelectRightPanelMode}
        onOpenSettings={onOpenSettings}
        onWorkbenchMenuOpenChange={setWorkbenchMenuOpen}
      />

      <div className="pane-row">
        <div className="pane-main workspace-main">
          <RoomChatMainPane
            isNew={isNew}
            sessionId={sessionId}
            avoidWorkbenchNotice={avoidWorkbenchNotice}
            locale={locale}
            inboxPendingCount={inboxPendingCount}
            inboxReloadKey={inboxReloadKey}
            discussPaused={discussPaused}
            decisionRuntime={decisionRuntime}
            showPlanApproval={showPlanApproval}
            verifiedLoopPendingApproval={verifiedLoopView.pendingApproval}
            firstOpenBlock={firstOpenBlock}
            consensusBlocked={consensusBlocked}
            planWorkflow={planWorkflow}
            planWorkflowPlanIntent={planWorkflowPlanIntent}
            showPlanWorkflowBanner={showPlanWorkflowBanner}
            showPlanWorkflowComposerHint={showPlanWorkflowComposerHint}
            recoveryVisible={recoveryVisible}
            recoveryLifecycleView={recoveryLifecycleView}
            recoveryBusyActionId={
              recoveryBusyAction ??
              (releasingLock ? "release_lock" : null) ??
              (discussRecoveryBusy ? "run_discuss_recovery" : null)
            }
            composerNoticeDismissed={composerNoticeDismissed}
            onOpenInbox={() => {
              setComposerNoticeDismissed("human_gate");
              openHumanInbox();
            }}
            onOpenWork={() => {
              setComposerNoticeDismissed("plan_workflow");
              openWorkApproval();
            }}
            onRecoveryAction={handleRecoveryAction}
            onRecoveryRetryAction={handleRecoveryRetryAction}
            onRecoveryDismiss={() => setRecoveryDismissedSig(recoverySignature)}
            onDismissNotice={setComposerNoticeDismissed}
            scrollRef={scrollRef}
            transcript={{
              sessionId,
              isNew,
              loading: loading ?? false,
              running,
              showPeerChannel,
              onPeerChannelChange: (on) => {
                setShowPeerChannel(on);
                setShowPeerChannelState(on);
              },
              visibleMessages,
              advisorRationales,
              openDraftMessageIds,
              pendingReplyAgents,
              runStartedAt,
              highlightChatLine,
              locale,
              transcriptLoading: localeMsg.transcriptLoading,
              transcriptEmpty: localeMsg.transcriptEmpty,
              transcriptEmptyHint: localeMsg.transcriptEmptyHint,
              showJumpButton,
              forceScrollButton: tweaks.forceScrollButton,
              scrollToBottom,
              transcriptActive,
              onActivityOpen: handleNotificationOpen,
            }}
            composerShell={{
              show: isNew || transcriptActive,
              tweaksPreflightDemo: tweaks.preflightDemo,
              recoveryItemsLength: recoveryItems.length,
              readiness,
              healthAgents,
              selected,
              clarifierQuestions,
              clarifierInterview,
              planWorkflowActive,
              planWorkflowPhase: planWorkflow?.phase,
              longRunning,
              running,
              onStop: handleStop,
              sessionId,
              eventStack: composerEventStack,
              sendReceipt,
              sendReceiptRaw,
              composerClassName,
              text,
              onTextChange: setText,
              onSend: handleSend,
              slashCommands,
              onSlashExecute: (cmd) => void runSlashCommand(cmd, cmd.slash),
              composerInputLocked,
              composerSendLocked,
              composerPlaceholder,
              pendingFiles,
              onFilesAdd: addFiles,
              onFileRemove: (id) =>
                setPendingFiles((f) => f.filter((x) => x.id !== id)),
              composerObjectionNotice,
              onFocusObjection: focusObjection,
              turnHint: composerEmergenceHint ?? composerPresetHint,
              costHint: composerCostHint,
              locale,
              roomPresets: visiblePresets,
              roomPreset,
              onRoomPresetSelect: selectRoomPreset,
              agents,
              onOpenModelPicker: () => {
                const command = slashCommands.find(
                  (candidate) => candidate.id === "model",
                );
                if (command) void executeSlashCommand(command, "");
              },
              choicePopover,
              authPopover,
              authPickerPopover,
              modelPopover: modelPopoverNode,
              commandHint,
            }}
            externalCommandConfirm={externalCommandConfirm}
            onExternalCommandDismiss={() => setExternalCommandConfirm(null)}
            onExternalCommandExecute={(command, args) => {
              void executeSlashCommand(command, args, true);
            }}
            permOpen={permOpen}
            showPermAlert={tweaks.showPermAlert}
            permissionSelectedAgents={
              tweaks.showPermAlert && !permOpen
                ? ["cursor", "claude"]
                : selected
            }
            onPermissionCancel={() => {
              tweaks.setShowPermAlert(false);
              setPermOpen(false);
              if (pendingSend) {
                setText(pendingSend.text);
                setPendingFiles(pendingSend.files);
                setPendingSend(null);
              }
            }}
            onPermissionConfirm={(permissions) => {
              tweaks.setShowPermAlert(false);
              setPermOpen(false);
              if (pendingSend) {
                void executeSend(
                  pendingSend.text,
                  pendingSend.files,
                  permissions,
                  composeMode,
                  pendingSend.turnProfile,
                );
                setPendingSend(null);
                setText("");
                setPendingFiles([]);
              }
            }}
          />
        </div>
      </div>

      <RoomChatInspector
        isNew={isNew}
        inspectorOpen={inspectorOpen}
        rightPanelMode={rightPanelMode}
        locale={locale}
        workbenchPanelWidth={workbenchPanelWidth}
        onWidthChange={setActiveWorkbenchWidth}
        onWidthCommit={commitWorkbenchWidth}
        onClose={toggleInspector}
        session={session}
        sessionId={sessionId}
        healthAgents={healthAgents}
        goalView={goalView}
        planMeta={planMeta}
        onFocusObjection={focusObjection}
        planExecutions={planExecutions}
        filesFocusPath={filesFocusPath}
        filesFocusRevision={filesFocusRevision}
      />
    </>
  );
}
