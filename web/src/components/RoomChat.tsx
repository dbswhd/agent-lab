import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  AgentOption,
  PlanWorkflowRecord,
  SessionDetail,
} from "../api/client";
import {
  cancelRoomRun,
  fetchCommands,
  postMissionDiscussRecovery,
  matchSlashCommand,
  releaseRoomRunLock,
  retryAgents,
  reconnectClaudeAuth,
  reconnectCursorBridge,
  reconnectKimiWorkBridge,
  runRoom,
  runSessionCommand,
  runGlobalCommand,
  SESSIONLESS_ACCOUNT_COMMAND_IDS,
  runRoomSlash,
  approveVerifiedLoop,
  approvePlan,
  rejectPlan,
  rejectVerifiedLoop,
  pauseMissionLoop,
  autoSyncSessionPlan,
  type AgentHealthRow,
  type AuthRunRef,
  type SlashCommandRecord,
} from "../api/client";
import { useInboxState } from "../hooks/useInboxState";
import { useGoalLoop } from "../hooks/useGoalLoop";
import { MacAlert } from "./MacAlert";
import { replayLiveLogToMessages } from "../utils/liveRoomLog";
import {
  mergePersistedChatWithLiveLog,
  preferRicherChatMessages,
} from "../utils/sessionChatMerge";
import { syncSessionActivityMarkers } from "../utils/transcriptActivity";
import {
  agentLabel,
  chatLineToMessage,
  isReplyWaitRole,
  parseTranscript,
  topicAsUserMessage,
} from "../utils/transcript";
import { CommandPalette } from "./CommandPalette";
import { workspacePaletteActions } from "../utils/commandPaletteActions";
import { useWorkspaceTabs } from "../hooks/useWorkspaceTabs";
import { useSessionRunState } from "../hooks/useSessionRunState";
import {
  PENDING_KEY,
  appendSessionMessages,
  clearBackgroundRun,
  finishSessionRun,
  finalizeCancelledTyping,
  getRunningSessionIds,
  getSessionRunSnapshot,
  hydrateSessionMessages,
  isSessionRunActive,
  markBackgroundRun,
  resetTurnRun,
  resolveRunSessionKey,
  syncRunStateFromLiveLog,
  updateSessionRun,
  type LiveMsg,
} from "../run/runSessionRegistry";
import { registerRoomEventHandler } from "../run/roomReconnectRegistry";
import { derivePendingReplyAgents } from "../run/runningAgents";
import { effectiveTurnAgents } from "../utils/agentMentions";
import { createRoomRunEventHandler } from "../hooks/useRoomSseHandler";
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
import { RoomTranscriptPanel } from "./RoomTranscriptPanel";
import { ComposerDecisionSurface } from "./ComposerDecisionSurface";
import { AutonomyDial } from "./AutonomyDial";
import { SlashCommandDivider } from "./SlashCommandDivider";
import { ComposerEventStack } from "./ComposerEventStack";
import { useHumanDecisionRuntime } from "../hooks/useHumanDecisionRuntime";
import { buildDecisionBlockedHeadline } from "../utils/decisionBlockedHeadline";
import { ChatComposer, type PendingFile } from "./ChatComposer";
import { ShellPortal } from "./ShellPortal";
import { ContextOverviewPanel } from "./ContextOverviewPanel";
import type { PlanApprovalMode, PlanRejectPayload } from "./PlanApprovalPanel";
import { type WorkFocusTarget } from "./WorkToolPanel";
import { AgentPermissionAlert } from "./AgentPermissionAlert";
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
import { roundDividerLabel } from "../utils/roundTopology";
import {
  resolveTurnSend,
  type ComposerTurnProfile,
} from "../utils/turnProfile";
import { sortAgentIds, sortAgentPickerOptions } from "../utils/agentOrder";
import {
  parseModelSlashArgs,
  readPendingRoomModels,
  readSessionRoomModels,
  writePendingRoomModels,
} from "../utils/modelSlash";
import { WorkspaceFilesPanel } from "./WorkspaceFilesPanel";
import { PreviewPanel } from "./PreviewPanel";
import { TerminalPanel } from "./TerminalPanel";
import { ComposerAuthFlowPopover } from "./ComposerAuthFlowPopover";
import { ComposerAuthPickerPopover } from "./ComposerAuthPickerPopover";
import { ComposerAuthSecretPopover } from "./ComposerAuthSecretPopover";
import { BackgroundTasksPanel } from "./BackgroundTasksPanel";
import type { ConsensusDryRunProposal } from "./ConsensusDryRunGateBar";
import { type ComposeMode } from "../utils/composeMode";
import { isPlanWorkflowAwaitingApproval } from "../utils/planComposerSync";
import { usePlanExecute } from "../hooks/usePlanExecute";
import { useLocale } from "../i18n/useLocale";
import { type StoredPlanAction } from "../utils/planExecuteHistory";
import {
  fetchSessionAgentCapabilities,
  fetchSessionSetupOptions,
  fetchSessionTasks,
  type RoomObjection,
  type RoomTasksPayload,
} from "../api/client";
import {
  capabilitiesForApi,
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
import type { WorkspacePreset } from "../utils/sessionSetup";
import {
  CUSTOM_WORKSPACE_ID,
  getStoredSessionTemplate,
  getStoredWorkspaceId,
  getStoredWorkspacePath,
  setStoredWorkspaceId,
  setStoredWorkspacePath,
} from "../utils/sessionSetup";
import {
  clearStoredAgentThreadBindings,
  getStoredAgentThreadBindings,
  type AgentThreadBindings,
} from "../utils/agentThreadBindings";
import {
  sendReceiptLabel,
  shouldShowSendReceiptOnChatTab,
} from "../utils/sendReceipt";
import { ComposerPreflightBar } from "./ComposerPreflightBar";
import { ReadinessComposerBar } from "./ReadinessComposerBar";
import { fetchReadiness, type ReadinessResponse } from "../api/client";
import {
  classifySendFailure,
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
  DEMO_PREFLIGHT_AGENTS,
} from "../utils/tweaksDemoFixtures";
import { useMessagesScroll } from "../hooks/useMessagesScroll";
import { WorkbenchPanel } from "./WorkbenchPanel";
import { WorkspaceChrome } from "./WorkspaceChrome";
import { DiffToolPanel } from "./DiffToolPanel";
import { ComposerChoicePopover } from "./ComposerChoicePopover";
import {
  ComposerModelPopover,
  type ModelPopoverAgent,
  type ModelPopoverSidePanel,
} from "./ComposerModelPopover";

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

function chatFingerprint(session: SessionDetail): string {
  const chat = session.chat;
  if (!chat?.length) {
    return `${session.id}:t:${session.transcript_md?.length ?? 0}:${session.topic}`;
  }
  const last = chat[chat.length - 1];
  return `${session.id}:${chat.length}:${last.ts ?? ""}:${last.content.length}`;
}

function attachmentSendTopic(files: PendingFile[]): string {
  if (files.length === 1) return `[첨부] ${files[0]!.file.name}`;
  return `[첨부] ${files.length}개 파일`;
}

function sessionToMessages(
  session: SessionDetail,
  reviewModeHint = false,
): LiveMsg[] {
  let out: LiveMsg[];
  if (session.chat && session.chat.length > 0) {
    out = [];
    let lastRound = 0;
    for (let i = 0; i < session.chat.length; i++) {
      const line = session.chat[i];
      if (line.role === "user") {
        lastRound = 0;
      }
      const pr = line.parallel_round ?? (line.role === "agent" ? 1 : 0);
      if (line.role === "agent" && pr >= 1 && pr !== lastRound) {
        out.push({
          id: `round-divider-${i}-${pr}`,
          role: "system",
          label: "",
          body: roundDividerLabel(pr, reviewModeHint),
          roundDivider: pr,
        });
        lastRound = pr;
      }
      out.push(chatLineToMessage(line, i));
    }
  } else if (session.live_log && session.live_log.length > 0) {
    const persisted =
      session.chat_total != null && session.chat_total > 0
        ? parseTranscript(session.transcript_md || "")
        : [];
    out =
      persisted.length > 0
        ? persisted
        : [
            topicAsUserMessage(session.topic || session.id),
            ...replayLiveLogToMessages(session.live_log, agentLabel),
          ];
  } else {
    out = [
      topicAsUserMessage(session.topic || session.id),
      ...parseTranscript(session.transcript_md || ""),
    ];
  }
  return mergePersistedChatWithLiveLog(out, session.live_log, agentLabel);
}

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
  const [, setSetupWorkspaces] = useState<WorkspacePreset[]>([]);
  const [workspaceId, setWorkspaceIdState] = useState(getStoredWorkspaceId);
  const [workspacePath, setWorkspacePathState] = useState<string | null>(
    getStoredWorkspacePath,
  );
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

  function setWorkspaceId(id: string, path?: string | null) {
    setWorkspaceIdState(id);
    setStoredWorkspaceId(id);
    if (path !== undefined) {
      setWorkspacePathState(path);
      setStoredWorkspacePath(path);
    }
  }

  useEffect(() => {
    fetchSessionSetupOptions()
      .then((opts) => {
        setSetupWorkspaces(opts.workspaces);
        const wsIds = new Set(opts.workspaces.map((w) => w.id));
        if (workspaceId !== CUSTOM_WORKSPACE_ID && !wsIds.has(workspaceId)) {
          setWorkspaceId(opts.defaults.workspace_id, null);
        }
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps -- hydrate once; stored ids validated against API
  }, []);

  useEffect(() => {
    const onPrefs = () => {
      setShowPeerChannelState(getShowPeerChannel());
    };
    window.addEventListener(TRANSCRIPT_VIEW_PREFS_EVENT, onPrefs);
    return () =>
      window.removeEventListener(TRANSCRIPT_VIEW_PREFS_EVENT, onPrefs);
  }, []);

  useEffect(() => {
    if (sessionId !== null) return;
    setWorkspaceIdState(getStoredWorkspaceId());
    setWorkspacePathState(getStoredWorkspacePath());
  }, [sessionId]);

  useEffect(() => {
    activeSessionIdRef.current = sessionId;
    if (sessionId !== null) {
      setLiveRunSessionKey(null);
    }
  }, [sessionId]);

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

  const applySessionScopedModels = useCallback((composition: string[]) => {
    const comp = sortAgentIds(composition);
    if (comp.length === 0) return;
    pendingSessionRoomModelsRef.current = comp;
    writePendingRoomModels(comp);
    setSelected(comp);
    agentsPickerInitRef.current = true;
    setCommandHint(`이 세션 동안 ${comp.join(", ")} 에이전트를 사용합니다.`);
  }, []);

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

  const executeSend = useCallback(
    async (
      msgText: string,
      filesToSend: PendingFile[],
      permissions: AgentPermissions,
      mode: ComposeMode = composeMode,
      profile: ComposerTurnProfile = turnProfile,
    ) => {
      if (mode === "execute") return;
      if (runBusy || running || synthesizing) return;
      const effectiveProfile: ComposerTurnProfile = roomPreset
        ? ((resolvedRoomPresets.find((p) => p.id === roomPreset)
            ?.turn_profile ?? profile) as ComposerTurnProfile)
        : profile;
      const roomMode = "discuss" as const;
      const {
        agents,
        agentRounds,
        reviewMode: useReviewMode,
        consensusMode: useConsensusMode,
      } = resolveTurnSend(effectiveProfile, selected);
      if (agents.length === 0) return;

      const pinnedRoomModels = !sessionId
        ? (pendingSessionRoomModelsRef.current ?? sortAgentIds(selected))
        : undefined;

      const sendText =
        msgText.trim() ||
        (filesToSend.length ? attachmentSendTopic(filesToSend) : "");
      if (!sendText) return;

      const attachmentNames = filesToSend.map((p) => p.file.name);
      const displayBody = msgText.trim();
      if (displayBody && filesToSend.length === 0) {
        lastPlainSendTextRef.current = displayBody;
      }
      setPendingFiles([]);

      const threadBindings = !sessionId
        ? (bootstrapAgentThreadBindings ??
          getStoredAgentThreadBindings() ??
          undefined)
        : undefined;
      const sessionTemplate = sessionId
        ? undefined
        : (bootstrapSessionTemplate ?? getStoredSessionTemplate());

      let runKey = resolveRunSessionKey(sessionId, activeSessionIdRef.current);
      const userMsg = topicAsUserMessage(
        displayBody,
        attachmentNames.length ? attachmentNames : undefined,
      );
      resetTurnRun(runKey, userMsg);
      clearRunWatchdog();
      scheduleLongRunHint();
      setRunLockStuck(false);
      setRecoveryFailure(null);
      setClarifierQuestions(null);
      const runScope = {
        runKey,
        activeSessionId: sessionId,
        userStopped: false,
        runFailed: false,
        lastSendReceipt: undefined as string | undefined,
      };
      runAbortRef.current?.abort();
      const runAbort = new AbortController();
      runAbortRef.current = runAbort;

      const onRoomEvent = createRoomRunEventHandler(runScope, {
        sessionId,
        profile: effectiveProfile,
        selected,
        mode,
        localeMsg,
        activeSessionIdRef,
        navigatedToSessionRef,
        pendingMissionTemplateRef,
        onSessionBind,
        onSessionChange,
        onSessionMetaRefresh,
        onBootstrapMissionTemplateApplied,
        setLiveRunSessionKey,
        persistPendingSessionRoomModels,
        openPlanTab,
        setRecoveryFailure,
        setRunLockStuck,
        setClarifierQuestions,
        setClarifierInterview,
        setDiscussPaused,
        setInboxReloadKey,
        setWorkHookAlert,
        setConsensusProposal,
        notifyConsensusSync,
        notifyConsensusFailure,
        pushMacNotification,
        refreshSessionMeta,
        refreshInboxPending,
        openHumanInbox,
        openWorkTab,
      });

      const onRoomEventWithRegistry = (ev: Record<string, unknown>) => {
        const evType = String(ev.type ?? "");
        if (evType === "start" && typeof ev.session_id === "string") {
          registerRoomEventHandler(ev.session_id, onRoomEventWithRegistry);
        }
        onRoomEvent(ev);
      };
      if (sessionId) {
        registerRoomEventHandler(sessionId, onRoomEventWithRegistry);
      }

      try {
        await runRoom(sendText, agents, onRoomEventWithRegistry, {
          sessionId: sessionId ?? undefined,
          files: filesToSend.map((p) => p.file),
          mode: roomMode,
          agentRounds,
          permissions,
          reviewMode: useReviewMode,
          consensusMode: useConsensusMode,
          turnProfile: effectiveProfile,
          researchMode: researchMode || effectiveProfile === "specialist",
          workspaceId: sessionId ? undefined : workspaceId,
          workspacePath:
            sessionId || workspaceId !== CUSTOM_WORKSPACE_ID
              ? undefined
              : (workspacePath ?? undefined),
          agentCapabilities: capabilitiesForApi(agentCapabilities),
          agentThreadBindings: threadBindings,
          sessionTemplate,
          roomPreset: roomPreset ?? undefined,
          roomModels: pinnedRoomModels,
          signal: runAbort.signal,
        });
        if (runScope.runFailed) {
          return;
        }
        if (!sessionId && pinnedRoomModels?.length) {
          pendingSessionRoomModelsRef.current = null;
          writePendingRoomModels(null);
        }
        if (!sessionId) {
          clearStoredAgentThreadBindings();
        }
        if (
          runScope.activeSessionId &&
          !navigatedToSessionRef.current &&
          !sessionId
        ) {
          activeSessionIdRef.current = runScope.activeSessionId;
          onSessionChange(runScope.activeSessionId);
        }
        if (
          (planComposeActive || runScope.lastSendReceipt === "plan_updated") &&
          (runScope.activeSessionId ?? sessionId)
        ) {
          openPlanTab();
        }
        setSendReceiptRaw(runScope.lastSendReceipt);
        setSendReceipt(
          sendReceiptLabel(
            runScope.lastSendReceipt,
            mode,
            runScope.userStopped,
            locale,
          ),
        );
        if (sendReceiptTimerRef.current != null) {
          window.clearTimeout(sendReceiptTimerRef.current);
        }
        sendReceiptTimerRef.current = window.setTimeout(() => {
          setSendReceipt(null);
          sendReceiptTimerRef.current = null;
        }, 5000);
      } catch (e) {
        const msg = String(e);
        if (runAbort.signal.aborted || msg.includes("aborted")) {
          runScope.userStopped = true;
        } else if (runScope.runFailed) {
          // SSE handler already set recovery (run lock / agent failure).
        } else {
          const detail = msg.replace(/^Error:\s*/, "");
          const classified = classifySendFailure(detail);
          setRecoveryFailure({
            source: classified.source,
            kind: classified.kind,
            message: detail,
          });
          if (classified.kind === "run_lock") {
            setRunLockStuck(true);
          } else if (
            msg.includes("already in progress") ||
            msg.includes("not ready")
          ) {
            setRunLockStuck(msg.includes("already in progress"));
          }
        }
      } finally {
        if (runAbortRef.current === runAbort) {
          runAbortRef.current = null;
        }
        if (runAbort.signal.aborted) {
          runScope.userStopped = true;
          void cancelRoomRun(
            runScope.activeSessionId ?? sessionId ?? undefined,
          ).catch(() => {});
        }
        if (runScope.userStopped) {
          finalizeCancelledTyping(runScope.runKey);
        }
        clearRunWatchdog();
        clearLongRunHint();
        finishSessionRun(
          runScope.runKey,
          runScope.activeSessionId ?? undefined,
        );
        const boundSid = runScope.activeSessionId ?? sessionId;
        if (boundSid && onSessionMetaRefresh && !runScope.runFailed) {
          void onSessionMetaRefresh(boundSid);
        }
        navigatedToSessionRef.current = false;
      }
    },
    [
      selected,
      sessionId,
      onSessionChange,
      onSessionBind,
      onSessionMetaRefresh,
      composeMode,
      turnProfile,
      researchMode,
      workspaceId,
      workspacePath,
      agentCapabilities,
      bootstrapAgentThreadBindings,
      bootstrapSessionTemplate,
      refreshSessionMeta,
      persistPendingSessionRoomModels,
      runBusy,
      running,
      synthesizing,
      roomPreset,
      resolvedRoomPresets,
    ],
  );

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
        await runRoom(
          "(plan synthesis)",
          selected,
          (ev) => {
            if (String(ev.type) === "error") {
              setRecoveryFailure({
                source: "run",
                message: String(ev.message ?? "plan synthesis failed"),
              });
            }
          },
          {
            sessionId,
            mode: "plan",
            agentRounds: 1,
            synthesizeOnly: true,
            requestId,
            permissions,
          },
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
    [selected, sessionId, synthesizing, onSessionChange, openPlanTab],
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

  const executeSlashCommand = useCallback(
    async (command: SlashCommandRecord, args: string, confirm = false) => {
      const sid = sessionId ?? activeSessionIdRef.current;
      const isGlobal = !sid && SESSIONLESS_ACCOUNT_COMMAND_IDS.has(command.id);
      if (!sid && !isGlobal) return;
      setCommandHint(null);
      setCommandChoices(null);
      setCommandScopeChoices(null);
      if (command.id !== "model") {
        setModelPopover(null);
      }
      try {
        const res = isGlobal
          ? await runGlobalCommand({
              command_id: command.id,
              args,
              confirm,
            })
          : await runSessionCommand(sid!, {
              command_id: command.id,
              args,
              confirm,
            });
        if (res.kind === "server") {
          const resultStage = res.result as
            | { stage?: unknown; auth_run?: unknown }
            | undefined;
          // Mirrors command_registry.py's _emit_slash_chat_line gate: only a
          // final action (no staged picker, no auth_run) is ever persisted to
          // chat.jsonl, so only that case gets a local divider. Appended here
          // (not just via refreshSessionMeta's later hydrate) because hydrate
          // is a no-op while a run is active — without this, sending a chat
          // message right after a slash command renders it before the
          // divider ever appears.
          if (
            sid &&
            res.text &&
            !resultStage?.stage &&
            !resultStage?.auth_run
          ) {
            appendSessionMessages(
              resolveRunSessionKey(sessionId, activeSessionIdRef.current),
              [
                {
                  id: `slash-divider-${crypto.randomUUID()}`,
                  role: "system",
                  label: "",
                  body: `[slash] ${res.text}`,
                },
              ],
            );
          }
          if (sid) {
            refreshSessionMeta();
          } else if (isGlobal) {
            void onRefreshHealth?.();
          }
          setCommandHint(res.text ?? "명령 실행 완료");
        } else if (res.kind === "external") {
          const payload = res.result as
            | { stdout?: string; detail?: string }
            | undefined;
          setCommandHint(
            (payload?.stdout ?? payload?.detail ?? "외부 명령 실행됨").slice(
              0,
              240,
            ),
          );
        } else if (res.text) {
          setCommandHint(res.text.slice(0, 240));
        } else if (res.detail) {
          setCommandHint(res.detail);
        } else {
          setCommandHint("명령 실행됨");
        }
        const stage = res.result as
          | {
              prompt?: string;
              stage?: string;
              composition?: string[];
              auto?: boolean;
              provider?: string;
              choices?: {
                kind?: string;
                provider?: string;
                current?: string[];
                composition?: string[];
                options: {
                  value: string;
                  label: string;
                  sublabel?: string;
                  selected?: boolean;
                  ready?: boolean;
                }[];
              };
              input?: { kind?: string; prefill?: string };
              auth_run?: AuthRunRef;
              updated?: boolean;
              model_updated?: boolean;
            }
          | undefined;
        if (stage?.auth_run) {
          setAuthRun(stage.auth_run);
          setCommandChoices(null);
          setCommandMultiChoices(null);
          setCommandScopeChoices(null);
          setCommandHint(null);
        }
        if (stage?.choices?.options?.length) {
          setCommandChoiceIndex(0);
          const choices = stage.choices;
          const kind = choices.kind ?? "provider";
          if (kind === "model_provider") {
            setModelPopover((prev) => ({
              command,
              autoEnabled: Boolean(stage.auto ?? prev?.autoEnabled),
              agents: prev?.agents ?? [],
              sidePanel: prev?.sidePanel ?? null,
            }));
            setCommandChoices(null);
            setCommandMultiChoices(null);
            setCommandScopeChoices(null);
            void executeSlashCommand(command, "compose");
          } else if (kind === "model_preset" || kind === "model_panel") {
            const providerId = stage.provider ?? choices.provider ?? "";
            const providerLabel = stage.prompt ?? "";
            const panelChoices = choices as {
              options: {
                value: string;
                label: string;
                selected?: boolean;
                available?: boolean;
                coming_soon_note?: string;
              }[];
              efforts?: string[];
              selected_model?: string;
              selected_effort?: string;
            };
            const presets = panelChoices.options.map((opt) => ({
              value: opt.value,
              label: opt.label,
              selected: opt.selected,
              available: opt.available,
              comingSoonNote: opt.coming_soon_note,
            }));
            setModelPopover((prev) => {
              const sidePanel: ModelPopoverSidePanel = {
                providerId,
                providerLabel,
                presets,
                efforts: panelChoices.efforts,
                selectedModel: panelChoices.selected_model,
                selectedEffort: panelChoices.selected_effort,
              };
              if (prev) {
                return {
                  ...prev,
                  autoEnabled: Boolean(stage.auto ?? prev.autoEnabled),
                  sidePanel,
                };
              }
              return {
                command,
                autoEnabled: Boolean(stage.auto),
                agents: [],
                sidePanel,
              };
            });
            setCommandChoices(null);
            setCommandMultiChoices(null);
            setCommandScopeChoices(null);
          } else if (kind === "multi") {
            if (command.id === "model") {
              const agents: ModelPopoverAgent[] = sortAgentPickerOptions(
                choices.options,
              ).map((opt) => ({
                value: opt.value,
                label: opt.label,
                ready: opt.ready,
              }));
              setMultiSelected(new Set(sortAgentIds(choices.current ?? [])));
              setModelPopover((prev) => ({
                command,
                autoEnabled: prev?.autoEnabled ?? false,
                agents,
                sidePanel: prev?.sidePanel ?? null,
              }));
              setCommandChoices(null);
              setCommandScopeChoices(null);
            } else {
              setCommandMultiChoices({
                command,
                argsPrefix: args,
                prompt: stage.prompt ?? res.text ?? "",
                current: sortAgentIds(stage.choices.current ?? []),
                options: sortAgentPickerOptions(stage.choices.options),
              });
              setMultiSelected(
                new Set(sortAgentIds(stage.choices.current ?? [])),
              );
              setCommandChoices(null);
              setCommandScopeChoices(null);
            }
          } else if (kind === "scope") {
            const composition =
              stage.composition ??
              stage.choices.composition ??
              args.split(",").filter(Boolean);
            setCommandScopeChoices({
              command,
              composition,
              prompt: stage.prompt ?? res.text ?? "",
              options: stage.choices.options,
            });
            setCommandMultiChoices(null);
            setCommandChoices(null);
          } else {
            setCommandChoices({
              command,
              argsPrefix: args,
              prompt: stage.prompt ?? res.text ?? "",
              kind,
              options: stage.choices.options,
            });
            setCommandMultiChoices(null);
            setCommandScopeChoices(null);
          }
          setCommandHint(null); // prompt is shown in the picker header instead
        } else {
          setCommandChoices(null);
          setCommandMultiChoices(null);
          setCommandScopeChoices(null);
        }
        if (stage?.updated && stage.composition?.length) {
          setSelected(sortAgentIds(stage.composition));
        }
        if (stage?.model_updated) {
          // Model/effort picks apply in place — the panel stays open (its
          // choices block above already refreshed it); only 적용 or an
          // outside click should dismiss the popover now.
          void onRefreshHealth?.();
        }
        if (stage?.input?.kind === "secret" && stage.input.prefill) {
          setSecretCommand({
            command,
            argsPrefix: stage.input.prefill.replace(/^\/login\s+/, ""),
            prompt: stage.prompt ?? "API 키 입력",
          });
          setSecretValue("");
          setText("");
          setCommandHint(null);
        } else if (stage?.input?.prefill) {
          setText(stage.input.prefill);
        } else if (command.id !== "model") {
          setText("");
        }
        void fetchCommands(isGlobal ? null : sid)
          .then((payload) => setSlashCommands(payload.commands ?? []))
          .catch(() => undefined);
      } catch (e) {
        const message = e instanceof Error ? e.message : "명령 실패";
        if (
          command.kind === "external" &&
          command.requires_human_confirm &&
          /confirm/i.test(message)
        ) {
          setExternalCommandConfirm({ command, args });
          return;
        }
        setCommandHint(message);
      }
    },
    [sessionId, refreshSessionMeta, onRefreshHealth],
  );

  const handleAuthRunComplete = useCallback(async () => {
    if (!authRun) return;
    const providerLabel =
      authRun.provider_id === "claude"
        ? "Claude"
        : authRun.provider_id === "codex"
          ? "Codex"
          : authRun.provider_id === "cursor"
            ? "Cursor"
            : authRun.provider_id;
    const actionLabel = authRun.action === "logout" ? "로그아웃" : "로그인";
    if (authRun.provider_id === "claude" && authRun.action === "login") {
      try {
        const res = await reconnectClaudeAuth();
        if (!sessionId) {
          setCommandHint(
            res.ok
              ? `${providerLabel} ${actionLabel} 완료`
              : (res.hint ?? `${providerLabel} ${actionLabel} 확인 필요`),
          );
          void fetchCommands(null)
            .then((payload) => setSlashCommands(payload.commands ?? []))
            .catch(() => undefined);
          void onRefreshHealth?.();
          return;
        }
        refreshSessionMeta();
        if (!res.ok && res.hint) {
          setCommandHint(res.hint);
        }
        return;
      } catch {
        /* fall through to generic completion hint */
      }
    }
    if (!sessionId) {
      setCommandHint(`${providerLabel} ${actionLabel} 완료`);
      void fetchCommands(null)
        .then((payload) => setSlashCommands(payload.commands ?? []))
        .catch(() => undefined);
      void onRefreshHealth?.();
      return;
    }
    refreshSessionMeta();
  }, [authRun, onRefreshHealth, refreshSessionMeta, sessionId]);

  useEffect(() => {
    if (!commandChoices) return;
    const onChoiceKey = (event: KeyboardEvent) => {
      const count = commandChoices.options.length;
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setCommandChoiceIndex((index) => (index + 1) % count);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setCommandChoiceIndex((index) => (index - 1 + count) % count);
      } else if (event.key === "PageDown") {
        event.preventDefault();
        setCommandChoiceIndex((index) => Math.min(index + 10, count - 1));
      } else if (event.key === "PageUp") {
        event.preventDefault();
        setCommandChoiceIndex((index) => Math.max(index - 10, 0));
      } else if (event.key === "Enter") {
        event.preventDefault();
        const option = commandChoices.options[commandChoiceIndex];
        if (option) {
          void executeSlashCommand(
            commandChoices.command,
            `${commandChoices.argsPrefix} ${option.value}`.trim(),
          );
        }
      }
    };
    document.addEventListener("keydown", onChoiceKey);
    return () => document.removeEventListener("keydown", onChoiceKey);
  }, [commandChoiceIndex, commandChoices, executeSlashCommand]);

  const runSlashCommand = useCallback(
    async (command: SlashCommandRecord, rawText?: string) => {
      setCommandHint(null);
      if (authRun && (command.id === "login" || command.id === "logout")) {
        setCommandHint("진행 중인 인증 패널을 먼저 닫아주세요.");
        return;
      }
      if (command.kind === "client") {
        if (command.id === "stop") handleStop();
        if (command.id === "focus-composer") focusComposerInput();
        setText("");
        return;
      }
      const parsed = rawText
        ? matchSlashCommand(rawText, slashCommands)
        : command;
      const target = parsed ?? command;
      const args = rawText ? rawText.replace(/^\/[^\s]+\s*/, "").trim() : "";
      if (!sessionId) {
        if (target.id === "model") {
          if (args) {
            const parsed = parseModelSlashArgs(args);
            const hasComposition =
              args.includes(",") ||
              parsed.scope != null ||
              (parsed.composition.length > 0 &&
                !["claude", "codex", "cursor", "kimi"].includes(
                  parsed.composition[0]?.split("|")[0] ?? "",
                ));
            if (hasComposition) {
              const next = sortAgentIds(
                parsed.composition.filter((id) =>
                  agents.some((agent) => agent.id === id),
                ),
              );
              if (next.length === 0) {
                setText("");
                setCommandHint("선택 가능한 에이전트가 없습니다.");
                return;
              }
              if (parsed.scope === "default") {
                setText("");
                void runRoomSlash(
                  `/model compose ${next.join(",")} default`,
                ).then(() => {
                  setCommandHint(
                    `기본값으로 저장했습니다 (${next.join(", ")}).`,
                  );
                });
                return;
              }
              if (parsed.scope === "session") {
                setText("");
                applySessionScopedModels(next);
                return;
              }
              setCommandScopeChoices({
                command: target,
                composition: next,
                prompt: `[${next.join(", ")}] — 적용 범위를 선택하세요`,
                options: [
                  {
                    value: "session",
                    label: "이번 세션만 (세션 동안 유지)",
                  },
                  {
                    value: "default",
                    label: "기본값으로 저장",
                  },
                ],
              });
              setText("");
              return;
            }
          }
          setText("");
          await executeSlashCommand(target, args);
          return;
        }
        if (!SESSIONLESS_ACCOUNT_COMMAND_IDS.has(target.id)) return;
      }
      if (
        target.kind === "external" &&
        target.requires_human_confirm !== false
      ) {
        setExternalCommandConfirm({ command: target, args });
        return;
      }
      await executeSlashCommand(target, args);
    },
    [
      agents,
      authRun,
      applySessionScopedModels,
      executeSlashCommand,
      handleStop,
      healthAgents,
      teamHealthAgents,
      selected,
      sessionId,
      slashCommands,
    ],
  );

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
  const decisionBlockedHeadline = useMemo(
    () =>
      buildDecisionBlockedHeadline({
        locale,
        inboxPendingCount,
        discussPaused,
        runtime: decisionRuntime,
        showPlanApproval,
        verifiedLoopPendingApproval: verifiedLoopView.pendingApproval,
        firstOpenBlock,
        consensusBlocked,
        planWorkflow,
      }),
    [
      locale,
      inboxPendingCount,
      discussPaused,
      decisionRuntime,
      showPlanApproval,
      verifiedLoopView.pendingApproval,
      firstOpenBlock,
      consensusBlocked,
      planWorkflow,
    ],
  );
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

  const modelPopoverNode = useMemo(() => {
    if (!modelPopover) return null;
    return (
      <ComposerModelPopover
        command={modelPopover.command}
        autoEnabled={modelPopover.autoEnabled}
        agents={modelPopover.agents}
        sidePanel={modelPopover.sidePanel}
        selectedAgents={multiSelected}
        onProviderDrill={(providerId) => {
          void executeSlashCommand(modelPopover.command, providerId);
        }}
        onSidePresetSelect={(providerId, value) => {
          void executeSlashCommand(
            modelPopover.command,
            `${providerId} ${value}`.trim(),
          );
        }}
        onSideEffortSelect={(providerId, effort) => {
          void executeSlashCommand(
            modelPopover.command,
            `${providerId} effort ${effort}`.trim(),
          );
        }}
        onSideClose={() =>
          setModelPopover((prev) =>
            prev ? { ...prev, sidePanel: null } : prev,
          )
        }
        onAgentToggle={(value) => {
          setMultiSelected((prev) => {
            const next = new Set(prev);
            if (next.has(value)) next.delete(value);
            else next.add(value);
            return next;
          });
        }}
        onAgentsApply={() => {
          const selected = sortAgentIds(
            modelPopover.agents
              .filter((opt) => multiSelected.has(opt.value))
              .map((opt) => opt.value),
          ).join(",");
          const cmd = modelPopover.command;
          setModelPopover(null);
          setMultiSelected(new Set());
          if (!sessionId) {
            const next = sortAgentIds(selected.split(",").filter(Boolean));
            if (next.length === 0) return;
            setCommandScopeChoices({
              command: cmd,
              composition: next,
              prompt: `[${next.join(", ")}] — 적용 범위를 선택하세요`,
              options: [
                {
                  value: "session",
                  label: "이번 세션만 (세션 동안 유지)",
                },
                {
                  value: "default",
                  label: "기본값으로 저장",
                },
              ],
            });
            return;
          }
          void executeSlashCommand(cmd, `compose ${selected}`.trim());
        }}
        onCancel={() => setModelPopover(null)}
      />
    );
  }, [executeSlashCommand, modelPopover, multiSelected, sessionId]);

  const authPopover = useMemo(() => {
    if (authRun) {
      return (
        <ComposerAuthFlowPopover
          run={authRun}
          onComplete={handleAuthRunComplete}
          onClose={() => {
            setAuthRun(null);
            focusComposerInput();
          }}
        />
      );
    }
    if (secretCommand) {
      return (
        <ComposerAuthSecretPopover
          prompt={secretCommand.prompt}
          value={secretValue}
          onChange={setSecretValue}
          onSubmit={() => {
            if (!secretValue.trim()) return;
            const args = `${secretCommand.argsPrefix} ${secretValue}`.trim();
            const cmd = secretCommand.command;
            setSecretCommand(null);
            setSecretValue("");
            void executeSlashCommand(cmd, args);
          }}
          onCancel={() => {
            setSecretCommand(null);
            setSecretValue("");
            focusComposerInput();
          }}
        />
      );
    }
    return null;
  }, [
    authRun,
    executeSlashCommand,
    handleAuthRunComplete,
    secretCommand,
    secretValue,
  ]);

  const authPickerPopover = useMemo(() => {
    if (!commandChoices) return null;
    const cmd = commandChoices.command;
    if (cmd.id !== "login" && cmd.id !== "logout") return null;
    const variant =
      commandChoices.kind === "auth_method" ? "methods" : "agents";
    return (
      <ComposerAuthPickerPopover
        action={cmd.id}
        title={commandChoices.prompt}
        variant={variant}
        options={commandChoices.options}
        highlightedIndex={commandChoiceIndex}
        onHighlight={setCommandChoiceIndex}
        onSelect={(value) =>
          void executeSlashCommand(
            commandChoices.command,
            `${commandChoices.argsPrefix} ${value}`.trim(),
          )
        }
        onCancel={() => setCommandChoices(null)}
      />
    );
  }, [commandChoiceIndex, commandChoices, executeSlashCommand]);

  const choicePopover = useMemo(() => {
    if (commandChoices) {
      const cmd = commandChoices.command;
      if (cmd.id === "login" || cmd.id === "logout") {
        return null;
      }
      return (
        <ComposerChoicePopover
          variant="single"
          command={commandChoices.command}
          prompt={commandChoices.prompt}
          options={commandChoices.options}
          highlightedIndex={commandChoiceIndex}
          onHighlight={setCommandChoiceIndex}
          onSelect={(value) =>
            void executeSlashCommand(
              commandChoices.command,
              `${commandChoices.argsPrefix} ${value}`.trim(),
            )
          }
          onCancel={() => setCommandChoices(null)}
        />
      );
    }
    if (commandScopeChoices) {
      return (
        <ComposerChoicePopover
          variant="scope"
          command={commandScopeChoices.command}
          prompt={commandScopeChoices.prompt}
          options={commandScopeChoices.options}
          onSelect={(value) => {
            const cmd = commandScopeChoices.command;
            const comp = commandScopeChoices.composition;
            const composition = comp.join(",");
            setCommandScopeChoices(null);
            if (!sessionId && cmd.id === "model") {
              if (value === "default") {
                void runRoomSlash(`/model compose ${composition} default`).then(
                  () => {
                    setCommandHint(`기본값으로 저장했습니다 (${composition}).`);
                  },
                );
              } else {
                applySessionScopedModels(comp);
              }
            } else {
              void executeSlashCommand(cmd, `${composition} ${value}`.trim());
            }
          }}
          onCancel={() => setCommandScopeChoices(null)}
        />
      );
    }
    if (commandMultiChoices) {
      return (
        <ComposerChoicePopover
          variant="multi"
          command={commandMultiChoices.command}
          prompt={commandMultiChoices.prompt}
          options={commandMultiChoices.options}
          selected={multiSelected}
          onToggle={(value) => {
            setMultiSelected((prev) => {
              const next = new Set(prev);
              if (next.has(value)) next.delete(value);
              else next.add(value);
              return next;
            });
          }}
          onApply={() => {
            const selected = sortAgentIds(
              commandMultiChoices.options
                .filter((opt) => multiSelected.has(opt.value))
                .map((opt) => opt.value),
            ).join(",");
            const cmd = commandMultiChoices.command;
            setCommandMultiChoices(null);
            setMultiSelected(new Set());
            if (!sessionId && cmd.id === "model") {
              const comp = selected.split(",").filter(Boolean);
              setCommandScopeChoices({
                command: cmd,
                composition: comp,
                prompt: `[${comp.join(", ")}] — 적용 범위를 선택하세요`,
                options: [
                  {
                    value: "session",
                    label: "이번 세션만 (세션 동안 유지)",
                  },
                  {
                    value: "default",
                    label: "기본값으로 저장",
                  },
                ],
              });
            } else {
              void executeSlashCommand(cmd, selected);
            }
          }}
          onCancel={() => {
            setCommandMultiChoices(null);
            setMultiSelected(new Set());
          }}
        />
      );
    }
    return null;
  }, [
    applySessionScopedModels,
    commandChoiceIndex,
    commandChoices,
    commandMultiChoices,
    commandScopeChoices,
    executeSlashCommand,
    sessionId,
  ]);

  const title = isNew ? "Session" : session?.topic || sessionId || "Session";
  const { view: autonomyView, loading: autonomyLoading } = useAutonomySession({
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

  return (
    <>
      <CommandPalette actions={paletteActions} />

      <WorkspaceChrome
        title={title}
        meta={titleMeta}
        headerExtra={
          sessionId ? (
            <AutonomyDial view={autonomyView} loading={autonomyLoading} />
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
          <div className="workspace-body">
            {!isNew && sessionId ? (
              <div
                className={`composer-notice-floating${
                  avoidWorkbenchNotice ? " composer-notice-floating--left" : ""
                }`}
              >
                <ComposerDecisionSurface
                  sessionId={sessionId}
                  inboxPendingCount={inboxPendingCount}
                  inboxReloadKey={inboxReloadKey}
                  discussPaused={discussPaused}
                  blockedHeadline={decisionBlockedHeadline}
                  recoveryVisible={recoveryVisible}
                  recoveryItems={recoveryLifecycleView.activeItems}
                  recoveryResolvedEvents={recoveryLifecycleView.resolvedEvents}
                  recoveryCanRetrySend={
                    recoveryLifecycleView.retryState.canFocusComposer
                  }
                  recoveryBusyActionId={
                    recoveryBusyAction ??
                    (releasingLock ? "release_lock" : null) ??
                    (discussRecoveryBusy ? "run_discuss_recovery" : null)
                  }
                  showPlanApproval={showPlanApproval}
                  showPlanWorkflowBanner={showPlanWorkflowBanner}
                  showPlanWorkflowComposerHint={showPlanWorkflowComposerHint}
                  planWorkflow={planWorkflow}
                  planWorkflowPlanIntent={planWorkflowPlanIntent}
                  dismissedKey={composerNoticeDismissed}
                  onOpenInbox={() => {
                    setComposerNoticeDismissed("human_gate");
                    openHumanInbox();
                  }}
                  onOpenWork={() => {
                    setComposerNoticeDismissed("plan_workflow");
                    openWorkApproval();
                  }}
                  onRecoveryAction={(actionId, item) =>
                    void handleRecoveryAction(actionId, item)
                  }
                  onRecoveryRetryAction={handleRecoveryRetryAction}
                  onRecoveryDismiss={() =>
                    setRecoveryDismissedSig(recoverySignature)
                  }
                  onDismissNotice={setComposerNoticeDismissed}
                />
              </div>
            ) : null}
            <div className="workspace-scroll scroll-y" ref={scrollRef}>
              <RoomTranscriptPanel
                sessionId={sessionId}
                isNew={isNew}
                loading={loading ?? false}
                running={running}
                showPeerChannel={showPeerChannel}
                onPeerChannelChange={(on) => {
                  setShowPeerChannel(on);
                  setShowPeerChannelState(on);
                }}
                visibleMessages={visibleMessages}
                advisorRationales={advisorRationales}
                openDraftMessageIds={openDraftMessageIds}
                pendingReplyAgents={pendingReplyAgents}
                runStartedAt={runStartedAt}
                highlightChatLine={highlightChatLine}
                locale={locale}
                transcriptLoading={localeMsg.transcriptLoading}
                transcriptEmpty={localeMsg.transcriptEmpty}
                transcriptEmptyHint={localeMsg.transcriptEmptyHint}
                showJumpButton={showJumpButton}
                forceScrollButton={tweaks.forceScrollButton}
                scrollToBottom={scrollToBottom}
                transcriptActive={transcriptActive}
                onActivityOpen={handleNotificationOpen}
              />
            </div>

            {isNew || transcriptActive ? (
              <>
                {tweaks.preflightDemo ? (
                  <ComposerPreflightBar
                    agents={DEMO_PREFLIGHT_AGENTS}
                    selected={["cursor"]}
                  />
                ) : recoveryItems.length === 0 ? (
                  <>
                    <ReadinessComposerBar readiness={readiness} />
                    <ComposerPreflightBar
                      agents={healthAgents}
                      selected={selected}
                    />
                  </>
                ) : null}
                <div className="composer-wrap">
                  {clarifierQuestions &&
                  clarifierQuestions.length > 0 &&
                  !(
                    planWorkflowActive &&
                    (planWorkflow?.phase === "CLARIFY" ||
                      planWorkflow?.phase === "INTAKE")
                  ) ? (
                    <div
                      className="clarifier-banner"
                      role="region"
                      aria-label="확인 질문"
                    >
                      <strong className="clarifier-banner__title">
                        {clarifierInterview?.plan_mode
                          ? "계획 확인 질문"
                          : "확인 질문"}
                      </strong>
                      <ul>
                        {(clarifierInterview?.questions?.length
                          ? clarifierInterview.questions
                          : clarifierQuestions.map((prompt) => ({
                              id: prompt,
                              prompt,
                            }))
                        ).map((q) => (
                          <li key={q.id ?? q.prompt}>
                            {"category" in q && q.category ? (
                              <span className="clarifier-banner__category">
                                {q.category}
                              </span>
                            ) : null}
                            {q.prompt ?? ""}
                          </li>
                        ))}
                      </ul>
                      <p className="clarifier-banner__hint">
                        답을 메시지에 포함해 다시 내면 에이전트가 시작됩니다.
                      </p>
                    </div>
                  ) : null}

                  {longRunning && running ? (
                    <div className="room-run-status" role="status">
                      <span className="room-run-status__hint">
                        장시간 실행 중...
                      </span>
                      <button
                        type="button"
                        className="mac-btn-secondary mac-btn-secondary--compact"
                        onClick={handleStop}
                      >
                        답변 중지
                      </button>
                    </div>
                  ) : null}

                  {sessionId ? (
                    <ComposerEventStack
                      sessionId={sessionId}
                      session={session}
                      planMd={planMd}
                      planMeta={planMeta}
                      planStaleNotice={workPlanStaleNotice}
                      workFocus={workFocus}
                      onWorkFocusHandled={() => setWorkFocus(null)}
                      synthesizing={synthesizing}
                      running={running}
                      runBusy={runBusy}
                      executeBusy={executeBusy}
                      onSynthesizeNow={handleSynthesizeNow}
                      onPlanRefClick={handlePlanRefClick}
                      onFocusTask={focusTask}
                      onFocusObjection={focusObjection}
                      onSessionUpdated={refreshSessionMeta}
                      roomTasks={roomTasks}
                      cursorReady={agents.some(
                        (a) => a.id === "cursor" && a.ready,
                      )}
                      executeError={planExecute.error}
                      planWorkflow={planWorkflow}
                      planApproval={
                        showPlanApproval
                          ? {
                              enabled: true,
                              workflowNotice: planWorkflow?.notice,
                              planGate: planWorkflow?.last_plan_gate ?? null,
                              canExecute:
                                planExecute.hasExecutableActions &&
                                planExecute.canDryRun &&
                                agents.some(
                                  (agent) =>
                                    agent.id === "cursor" && agent.ready,
                                ),
                              busy: verifiedLoopBusy || running || runBusy,
                              error: verifiedLoopError,
                              onApprove: (mode) =>
                                void handleVerifiedApprove(mode),
                              onReject: (payload) =>
                                void handleVerifiedReject(payload),
                            }
                          : null
                      }
                      workHookAlert={workHookAlert}
                      onDismissWorkHookAlert={() => setWorkHookAlert(null)}
                      inboxPendingCount={inboxPendingCount}
                      inboxReloadKey={inboxReloadKey}
                      currentPlanRevision={currentPlanRevision}
                      onInboxResolved={handleInboxResolved}
                      onInboxBuildStarted={handleInboxBuildStarted}
                      onInboxRefClick={handleInboxRefClick}
                      execPending={execPendingForBar}
                      storedActions={
                        (session?.run?.actions as StoredPlanAction[]) ?? []
                      }
                      onExecuteApprove={() => {
                        if (demoExecPending) {
                          pushMacNotification({
                            title: "Execute (demo)",
                            body: "승인 시뮬레이트",
                          });
                          return;
                        }
                        void planExecute.approve();
                      }}
                      onExecuteReject={() => {
                        if (demoExecPending) {
                          pushMacNotification({
                            title: "Execute (demo)",
                            body: "거부 시뮬레이트",
                          });
                          return;
                        }
                        void planExecute.reject();
                      }}
                      showExecuteQueue={showExecuteQueueStrip}
                      consensusProposal={consensusForBar}
                      showConsensusGate={showConsensusDryRunGate}
                      consensusGateBusy={consensusGateBusy}
                      onConsensusDryRun={
                        tweaks.consensusGateDemo
                          ? () =>
                              pushMacNotification({
                                title: "Consensus (demo)",
                                body: "Dry-run 시뮬레이트",
                              })
                          : handleConsensusDryRun
                      }
                      onConsensusDismiss={
                        tweaks.consensusGateDemo
                          ? () => tweaks.setConsensusGateDemo(false)
                          : dismissConsensusProposal
                      }
                      onOpenDiff={openDiffTab}
                      onOpenFiles={openFilesTab}
                      onOpenFile={openFileInWorkbench}
                      disabled={running || synthesizing || runBusy}
                    />
                  ) : null}

                  {sendReceipt &&
                  shouldShowSendReceiptOnChatTab(
                    sendReceipt,
                    sendReceiptRaw,
                  ) ? (
                    <div className="composer-send-receipt" role="status">
                      {sendReceipt}
                    </div>
                  ) : null}

                  <ChatComposer
                    className={
                      [
                        turnProfile === "review"
                          ? "composer--review"
                          : undefined,
                        turnProfile === "loop" ? "composer--free" : undefined,
                        composerModeVariant === "consensus"
                          ? "composer--consensus-mode"
                          : undefined,
                        composerModeVariant === "plan"
                          ? "composer--plan-mode"
                          : undefined,
                        composerModeVariant === "discuss"
                          ? "composer--discuss-mode"
                          : undefined,
                      ]
                        .filter(Boolean)
                        .join(" ") || undefined
                    }
                    value={text}
                    onChange={setText}
                    onSend={handleSend}
                    slashCommands={slashCommands}
                    onSlashExecute={(cmd) =>
                      void runSlashCommand(cmd, cmd.slash)
                    }
                    disabled={composerInputLocked}
                    sendDisabled={composerSendLocked}
                    placeholder={composerPlaceholder}
                    showModeChipHint={false}
                    running={running}
                    onStop={handleStop}
                    files={pendingFiles}
                    onFilesAdd={addFiles}
                    onFileRemove={(id) =>
                      setPendingFiles((f) => f.filter((x) => x.id !== id))
                    }
                    objectionNotice={composerObjectionNotice}
                    onFocusObjection={focusObjection}
                    turnHint={composerEmergenceHint ?? composerPresetHint}
                    costHint={composerCostHint}
                    locale={locale}
                    sessionId={sessionId}
                    roomPresets={visiblePresets}
                    roomPreset={roomPreset}
                    onRoomPresetSelect={selectRoomPreset}
                    activeModels={sortAgentIds(selected)
                      .map((id) => agents.find((agent) => agent.id === id))
                      .filter((agent): agent is AgentOption => Boolean(agent))}
                    onOpenModelPicker={() => {
                      const command = slashCommands.find(
                        (candidate) => candidate.id === "model",
                      );
                      if (command) void executeSlashCommand(command, "");
                    }}
                    choicePopover={choicePopover}
                    authPopover={authPopover}
                    authPickerPopover={authPickerPopover}
                    modelPopover={modelPopoverNode}
                  />

                  {commandHint ? (
                    <SlashCommandDivider
                      text={commandHint}
                      className="composer-slash-divider"
                    />
                  ) : null}
                </div>
              </>
            ) : null}

            <MacAlert
              open={externalCommandConfirm !== null}
              title="외부 명령 실행"
              message={
                externalCommandConfirm
                  ? `${externalCommandConfirm.command.label} (${externalCommandConfirm.command.slash}) — 로컬 subprocess를 실행합니다. Settings에서 allowlist에 포함된 명령만 실행됩니다.`
                  : undefined
              }
              buttons={[
                {
                  label: "취소",
                  variant: "cancel",
                  onClick: () => setExternalCommandConfirm(null),
                },
                {
                  label: "실행",
                  variant: "primary",
                  onClick: () => {
                    const pending = externalCommandConfirm;
                    setExternalCommandConfirm(null);
                    if (pending) {
                      void executeSlashCommand(
                        pending.command,
                        pending.args,
                        true,
                      );
                    }
                  },
                },
              ]}
              onClose={() => setExternalCommandConfirm(null)}
            />

            <AgentPermissionAlert
              open={permOpen || tweaks.showPermAlert}
              selectedAgents={
                tweaks.showPermAlert && !permOpen
                  ? ["cursor", "claude"]
                  : selected
              }
              onCancel={() => {
                tweaks.setShowPermAlert(false);
                setPermOpen(false);
                if (pendingSend) {
                  setText(pendingSend.text);
                  setPendingFiles(pendingSend.files);
                  setPendingSend(null);
                }
              }}
              onConfirm={(permissions) => {
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
                  // Clear the composer once the send is dispatched — the
                  // non-permission path clears in handleSend, this path didn't.
                  setText("");
                  setPendingFiles([]);
                }
              }}
            />
          </div>
        </div>
      </div>

      {!isNew && inspectorOpen ? (
        <ShellPortal>
          <WorkbenchPanel
            mode={rightPanelMode}
            locale={locale}
            open={inspectorOpen}
            width={workbenchPanelWidth}
            onWidthChange={setActiveWorkbenchWidth}
            onWidthCommit={commitWorkbenchWidth}
            onClose={toggleInspector}
          >
            {rightPanelMode === "overview" && session ? (
              <ContextOverviewPanel
                session={session}
                sessionId={sessionId}
                healthAgents={healthAgents}
                goalView={goalView}
                planMeta={planMeta}
                onFocusObjection={focusObjection}
              />
            ) : null}
            {rightPanelMode === "background" && sessionId ? (
              <BackgroundTasksPanel sessionId={sessionId} />
            ) : null}
            {rightPanelMode === "diff" ? (
              <DiffToolPanel executions={planExecutions} />
            ) : null}
            {rightPanelMode === "files" && sessionId ? (
              <WorkspaceFilesPanel
                sessionId={sessionId}
                focusPath={filesFocusPath}
                focusRevision={filesFocusRevision}
              />
            ) : null}
            {rightPanelMode === "preview" && sessionId ? (
              <PreviewPanel sessionId={sessionId} />
            ) : null}
            {rightPanelMode === "terminal" && sessionId ? (
              <TerminalPanel sessionId={sessionId} />
            ) : null}
          </WorkbenchPanel>
        </ShellPortal>
      ) : null}
    </>
  );
}
