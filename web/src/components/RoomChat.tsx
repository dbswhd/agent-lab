import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  AgentOption,
  PlanWorkflowRecord,
  SessionDetail,
} from "../api/client";
import {
  cancelRoomRun,
  matchSlashCommand,
  pauseMissionLoop,
  runRoomSlash,
  type AgentHealthRow,
} from "../api/client";
import { useInboxState } from "../hooks/useInboxState";
import { useGoalLoop } from "../hooks/useGoalLoop";
import { preferRicherChatMessages } from "../utils/sessionChatMerge";
import { syncSessionActivityMarkers } from "../utils/transcriptActivity";
import { isReplyWaitRole } from "../utils/transcript";
import { CommandPalette } from "./CommandPalette";
import { useWorkspaceTabs } from "../hooks/useWorkspaceTabs";
import { useSessionRunState } from "../hooks/useSessionRunState";
import {
  PENDING_KEY,
  finalizeCancelledTyping,
  getRunningSessionIds,
  getSessionRunSnapshot,
  hydrateSessionMessages,
  isSessionRunActive,
  resolveRunSessionKey,
  syncRunStateFromLiveLog,
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
import { type WorkFocusTarget } from "./WorkToolPanel";
import { useMacNotifications } from "../hooks/useMacNotifications";
import {
  agentsNeedingPermissionPrompt,
  hasSavedPermissionDefaults,
  roomPermissions,
} from "../utils/agentPermissions";
import { dispatchNotification } from "../utils/pushNotification";
import { executionApprovalGate } from "../utils/executeApprovalGate";
import { notifyDesktop } from "../utils/desktopNotify";
import { buildPlanMetaView } from "../utils/planMeta";
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
import { writePendingRoomModels } from "../utils/modelSlash";
import { isPlanWorkflowAwaitingApproval } from "../utils/planComposerSync";
import { usePlanExecute } from "../hooks/usePlanExecute";
import { useLocale } from "../i18n/useLocale";
import {
  fetchSessionTasks,
  type RoomObjection,
  type RoomTasksPayload,
} from "../api/client";
import {
  findChatLineIndexForTask,
  messageMentionsTask,
} from "../utils/taskBarCopy";
import { CUSTOM_WORKSPACE_ID } from "../utils/sessionSetup";
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
import { RoomChatMainPane } from "./RoomChatMainPane";
import { RoomChatInspector } from "./RoomChatInspector";
import {
  chatFingerprint,
  sessionToMessages,
} from "../utils/roomSessionMessages";
import { type AgentThreadBindings } from "../utils/agentThreadBindings";
import { fetchReadiness, type ReadinessResponse } from "../api/client";
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
  const navigatedToSessionRef = useRef(false);
  const agentsPickerInitRef = useRef(false);
  const { agentCapabilities } = useRoomAgentCapabilities({
    sessionId,
    sessionRun: session?.run as Record<string, unknown> | undefined,
    selected,
    pendingSessionRoomModelsRef,
    agentsPickerInitRef,
    setSelected,
  });

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

  const { handleNotificationOpen } = useRoomNotificationRouting({
    focusWorkStack,
    setRightPanelMode,
    onOpenSettings,
  });

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
    executeError: planExecute.error,
    planExecutions: planExecutions,
    composerSendLocked,
    onResolutionNotify: notifyRecoveryResolution,
  });

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
