import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  AgentOption,
  PlanActionItem,
  PlanWorkflowRecord,
  SessionDetail,
} from "../api/client";
import {
  applySessionTemplate,
  cancelRoomRun,
  pauseMissionLoop,
  checkSessionGoal,
  fetchCommands,
  fetchInboxSummary,
  fetchSessionInbox,
  postMissionDiscussRecovery,
  matchSlashCommand,
  releaseRoomRunLock,
  runRoom,
  runSessionCommand,
  setSessionGoal,
  approveVerifiedLoop,
  approvePlan,
  rejectPlan,
  rejectVerifiedLoop,
  autoSyncSessionPlan,
  type AgentHealthRow,
  type SlashCommandRecord,
} from "../api/client";
import { MacAlert } from "./MacAlert";
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
  finishSessionRun,
  getRunningSessionIds,
  hydrateSessionMessages,
  isSessionRunActive,
  migratePendingSessionRun,
  resetTurnRun,
  resolveRunSessionKey,
  updateSessionRun,
  type LiveMsg,
} from "../run/runSessionRegistry";
import { patchTurnMessages } from "../run/runSessionSsePatch";
import { deriveRunningAgentSlots } from "../run/runningAgents";
import { LiveAgentsStrip } from "./LiveAgentsStrip";
import {
  getInspectorOpen,
  getLastRightPanelMode,
  getWorkbenchPanelWidth,
  setInspectorOpen,
  setLastRightPanelMode,
  setWorkbenchPanelWidth,
} from "../utils/inspectorPanePrefs";
import {
  getShowHumanSynthesis,
  getShowPeerChannel,
  setShowHumanSynthesis,
  setShowPeerChannel,
  TRANSCRIPT_VIEW_PREFS_EVENT,
} from "../utils/transcriptViewPrefs";
import { TranscriptViewOptions } from "./TranscriptViewOptions";
import { ChatBubble, ReplyWaitingBubble } from "./ChatBubble";
import { HumanInboxPanel } from "./HumanInboxPanel";
import { DiscussInboxPanel } from "./DiscussInboxPanel";
import { DiscussRecoveryBanner } from "./DiscussRecoveryBanner";
import { HumanDecisionBanner } from "./HumanDecisionBanner";
import { ChatComposer, type PendingFile } from "./ChatComposer";
import { ShellPortal } from "./ShellPortal";
import { NotificationCenter } from "./NotificationCenter";
import { useNotificationUnread } from "../hooks/useNotificationUnread";
import { ContextOverviewPanel } from "./ContextOverviewPanel";
import { ContextTasksPanel } from "./ContextTasksPanel";
import { GoalLoopBanner } from "./GoalLoopBanner";
import { PlanApprovalPanel } from "./PlanApprovalPanel";
import { PlanWorkflowBanner } from "./PlanWorkflowBanner";
import { VerifiedLoopBanner } from "./VerifiedLoopBanner";
import { WorkToolPanel } from "./WorkToolPanel";
import { HumanGatePanel } from "./HumanGatePanel";
import { AgentPermissionAlert } from "./AgentPermissionAlert";
import { useMacNotifications } from "../hooks/useMacNotifications";
import type { AgentPermissions } from "../utils/agentPermissions";
import {
  agentsNeedingPermissionPrompt,
  hasSavedPermissionDefaults,
  roomPermissions,
} from "../utils/agentPermissions";
import {
  agreementPlanSyncedLabel,
  agreementPlanSyncFailedLabel,
  consensusDryRunNotifyBody,
  consensusDryRunNotifyTitle,
  latestPendingConsensusAgreement,
} from "../utils/consensusAgreement";
import { dispatchNotification } from "../utils/pushNotification";
import {
  formatDispatchActivityLine,
  formatEnvelopeActivityLine,
  formatHookActivityLine,
  isExecutionRelevantHook,
} from "../utils/hookActivity";
import {
  notificationActionForKind,
  subscribeNotificationActions,
} from "../utils/notificationActions";
import type { AppNotification } from "../utils/notificationStore";
import { executionApprovalGate } from "../utils/executeApprovalGate";
import { notifyDesktop } from "../utils/desktopNotify";
import { buildPlanMetaView, composerPlanStaleNotice } from "../utils/planMeta";
import { buildGoalLoopView } from "../utils/goalLoopView";
import { buildVerifiedLoopView } from "../utils/verifiedLoopView";
import { activateInboxRef } from "../utils/inboxRefNavigation";
import {
  isPlanWorkflowPhaseBanner,
  isPlanWorkflowComposerHint,
  planWorkflowPhaseTranscriptLine,
} from "../utils/planWorkflowView";
import {
  consensusIncompleteLabel,
  roundDividerLabel,
} from "../utils/roundTopology";
import {
  composerTurnHint,
  normalizeTurnProfile,
  resolveTurnSend,
  setTurnProfile,
  type ComposerTurnProfile,
} from "../utils/turnProfile";
import { WorkspaceFilesPanel } from "./WorkspaceFilesPanel";
import { PreviewPanel } from "./PreviewPanel";
import { TerminalPanel } from "./TerminalPanel";
import { BackgroundTasksPanel } from "./BackgroundTasksPanel";
import { ExecuteQueueBar } from "./ExecuteQueueBar";
import { ConsensusDryRunGateBar } from "./ConsensusDryRunGateBar";
import type { ConsensusDryRunProposal } from "./ConsensusDryRunGateBar";
import {
  getPlanAfterSend,
  getPlanAfterSendForSession,
  setPlanAfterSendForSession,
  setTurnStrategy,
  getTurnStrategy,
  type ComposeMode,
} from "../utils/composeMode";
import {
  isPlanWorkflowAwaitingApproval,
  suggestPlanToggleForWorkflow,
} from "../utils/planComposerSync";
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
import { RoomTaskBar } from "./RoomTaskBar";
import {
  findChatLineIndexForTask,
  focusComposerInput,
  lastTurnHadConsensusMode,
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
import { ScrollToBottomButton } from "./ScrollToBottomButton";
import { useMessagesScroll } from "../hooks/useMessagesScroll";
import { WorkbenchPanel } from "./WorkbenchPanel";
import { WorkspaceChrome } from "./WorkspaceChrome";
import { DiffToolPanel } from "./DiffToolPanel";

const LONG_RUN_HINT_MS = Number(
  import.meta.env.VITE_ROOM_LONG_RUN_HINT_MS || "180000",
);

type Props = {
  agents: AgentOption[];
  healthAgents?: AgentHealthRow[];
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
  if (session.chat && session.chat.length > 0) {
    const out: LiveMsg[] = [];
    let lastRound = 0;
    for (let i = 0; i < session.chat.length; i++) {
      const line = session.chat[i];
      const pr = line.parallel_round ?? (line.role === "agent" ? 1 : 0);
      if (line.role === "agent" && pr >= 1 && pr !== lastRound) {
        out.push({
          id: `round-divider-${pr}`,
          role: "system",
          label: "",
          body: roundDividerLabel(pr, reviewModeHint),
          roundDivider: pr,
        });
        lastRound = pr;
      }
      out.push(chatLineToMessage(line, i));
    }
    return out;
  }
  return [
    topicAsUserMessage(session.topic || session.id),
    ...parseTranscript(session.transcript_md || ""),
  ];
}

export function RoomChat({
  agents,
  healthAgents = [],
  sessionId,
  session,
  loading,
  onSessionChange,
  onSessionBind,
  onSessionMetaRefresh,
  sidebarOpen: _sidebarOpen,
  onToggleSidebar: _onToggleSidebar,
  onOpenSettings,
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
  const tweaks = useTweaksDemoOptional() ?? TWEAKS_DEMO_OFF;
  const [selected, setSelected] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  /** SSE start assigns a real session id before App props catch up. */
  const [liveRunSessionKey, setLiveRunSessionKey] = useState<string | null>(
    null,
  );
  const runSessionKey = sessionId ?? liveRunSessionKey ?? PENDING_KEY;
  const { messages, running, runBusy, synthesizing, setSynthesizing } =
    useSessionRunState(runSessionKey);
  const [error, setError] = useState<string | null>(null);
  const [planActionFocusIndex, setPlanActionFocusIndex] = useState<
    number | null
  >(null);
  const [showPeerChannel, setShowPeerChannelState] =
    useState(getShowPeerChannel);
  const [showHumanSynthesis, setShowHumanSynthesisState] = useState(
    getShowHumanSynthesis,
  );
  const [workHookAlert, setWorkHookAlert] = useState<{
    event: string;
    body: string;
    blocked: boolean;
  } | null>(null);
  const [inspectorOpen, setInspectorOpenState] = useState(getInspectorOpen);
  const [workbenchPanelWidth, setWorkbenchPanelWidthState] = useState(
    getWorkbenchPanelWidth,
  );
  const [roomTasks, setRoomTasks] = useState<RoomTasksPayload | null>(null);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [planMd, setPlanMd] = useState("");
  const [permOpen, setPermOpen] = useState(false);
  const [turnProfile, setTurnProfileState] =
    useState<ComposerTurnProfile>(getTurnStrategy);
  const [planAfterSend, setPlanAfterSendState] = useState(getPlanAfterSend);
  const composeMode: ComposeMode = planAfterSend ? "plan" : "discuss";
  const [researchMode] = useState(() => {
    try {
      return localStorage.getItem("agent-lab-research-mode") === "1";
    } catch {
      return false;
    }
  });
  const { locale, msg: localeMsg } = useLocale();
  const composerModeVariant = useMemo((): "discuss" | "plan" | "consensus" => {
    const profile = resolveTurnSend(turnProfile, selected);
    if (profile.consensusMode) return "consensus";
    if (planAfterSend) return "plan";
    return "discuss";
  }, [turnProfile, selected, planAfterSend]);
  const composerTurnHintLine = useMemo(
    () => composerTurnHint(turnProfile, selected, locale),
    [turnProfile, selected, locale],
  );
  const modeChipCopy = useMemo(() => {
    const wf = session?.run?.plan_workflow as PlanWorkflowRecord | undefined;
    const wfActive = Boolean(wf?.enabled);
    if (composerModeVariant === "plan") {
      return { label: localeMsg.modePlan, hint: localeMsg.modePlanHint };
    }
    if (composerModeVariant === "consensus") {
      return {
        label: localeMsg.modeConsensus,
        hint: localeMsg.modeConsensusHint,
      };
    }
    if (wfActive && wf?.phase && wf.phase !== "APPROVED") {
      return {
        label: localeMsg.modeDiscuss,
        hint: localeMsg.planWorkflowSideDiscussHint(wf.phase),
      };
    }
    return { label: localeMsg.modeDiscuss, hint: localeMsg.modeDiscussHint };
  }, [composerModeVariant, localeMsg, session?.run?.plan_workflow]);
  const [pendingSend, setPendingSend] = useState<{
    text: string;
    files: PendingFile[];
    turnProfile: ComposerTurnProfile;
    planAfterSend: boolean;
  } | null>(null);
  const [goalText, setGoalText] = useState("");
  const [goalBusy, setGoalBusy] = useState(false);
  const [goalError, setGoalError] = useState<string | null>(null);
  const [verifiedEditGoal, setVerifiedEditGoal] = useState("");
  const [verifiedEditCriteria, setVerifiedEditCriteria] = useState("");
  const [verifiedEditPromise, setVerifiedEditPromise] = useState("DONE");
  const [verifiedLoopBusy, setVerifiedLoopBusy] = useState(false);
  const [verifiedLoopError, setVerifiedLoopError] = useState<string | null>(
    null,
  );
  const [highlightChatLine, setHighlightChatLine] = useState<number | null>(
    null,
  );
  const [taskBarFocusObjection, setTaskBarFocusObjection] = useState<{
    id: string;
    nonce: number;
  } | null>(null);
  const highlightTimerRef = useRef<number | null>(null);
  const [sendReceipt, setSendReceipt] = useState<string | null>(null);
  const [sendReceiptRaw, setSendReceiptRaw] = useState<string | undefined>();
  const [hideApprovedPlanBanner, setHideApprovedPlanBanner] = useState(false);
  const [inboxPendingCount, setInboxPendingCount] = useState(0);
  const [globalInboxPending, setGlobalInboxPending] = useState(0);
  const [inboxReloadKey, setInboxReloadKey] = useState(0);
  const [discussRecoveryBusy, setDiscussRecoveryBusy] = useState(false);
  const [inboxSegment, setInboxSegment] = useState<
    "all" | "discuss" | "activity" | "questions" | "build" | "skills"
  >("all");
  const [discussPaused, setDiscussPaused] = useState(false);
  const [humanDecisionBannerVisible, setHumanDecisionBannerVisible] =
    useState(false);
  const [showInboxPopup, setShowInboxPopup] = useState(false);
  const [workFocus, setWorkFocus] = useState<"execute" | "plan" | null>(null);
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
  const [slashCommands, setSlashCommands] = useState<SlashCommandRecord[]>([]);
  const [commandHint, setCommandHint] = useState<string | null>(null);
  const [externalCommandConfirm, setExternalCommandConfirm] = useState<{
    command: SlashCommandRecord;
    args: string;
  } | null>(null);
  const runWatchdogRef = useRef<number | null>(null);
  const syncedChatRef = useRef("");
  const [, setSetupWorkspaces] = useState<WorkspacePreset[]>([]);
  const [workspaceId, setWorkspaceIdState] = useState(getStoredWorkspaceId);
  const [workspacePath, setWorkspacePathState] = useState<string | null>(
    getStoredWorkspacePath,
  );
  const [consensusProposal, setConsensusProposal] =
    useState<ConsensusDryRunProposal | null>(null);
  const [consensusGateBusy, setConsensusGateBusy] = useState(false);
  const [, setLongRunning] = useState(false);
  const [, setRunLockStuck] = useState(false);
  const [, setReleasingLock] = useState(false);
  const longRunHintRef = useRef<number | null>(null);
  const [agentCapabilities, setAgentCapabilities] =
    useState<AgentCapabilitiesMap>(() =>
      cloneCapabilities(DEFAULT_AGENT_CAPABILITIES),
    );
  const [, setResolvedAgentCwd] = useState<Record<string, string>>({});
  const activeSessionIdRef = useRef<string | null>(sessionId);
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
      setShowHumanSynthesisState(getShowHumanSynthesis());
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
    agentsPickerInitRef.current = false;
  }, [sessionId]);

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

  function changeTurnProfile(profile: ComposerTurnProfile) {
    setTurnProfileState(profile);
    setTurnStrategy(profile);
    setTurnProfile(profile);
  }

  function changePlanAfterSend(on: boolean) {
    setPlanAfterSendState(on);
    setPlanAfterSendForSession(sessionId ?? activeSessionIdRef.current, on);
  }

  const planToggleSyncedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setPlanAfterSendState(getPlanAfterSend());
      return;
    }
    const wf = session?.run?.plan_workflow as PlanWorkflowRecord | undefined;
    if (isPlanWorkflowAwaitingApproval(wf)) {
      setPlanAfterSendState(false);
      setPlanAfterSendForSession(sessionId, false);
      return;
    }
    const syncKey = `${sessionId}:${(wf?.phase ?? "none").toUpperCase()}:${wf?.enabled ? "1" : "0"}`;
    if (planToggleSyncedRef.current === syncKey) return;
    planToggleSyncedRef.current = syncKey;
    const suggested = suggestPlanToggleForWorkflow(wf);
    if (suggested !== null) {
      setPlanAfterSendState(suggested);
      setPlanAfterSendForSession(sessionId, suggested);
    } else {
      setPlanAfterSendState(getPlanAfterSendForSession(sessionId));
    }
  }, [sessionId, session?.run?.plan_workflow]);

  const refreshTasks = useCallback(
    (overrideId?: string | null) => {
      const sid = overrideId ?? sessionId ?? activeSessionIdRef.current;
      if (!sid) {
        setRoomTasks(null);
        return;
      }
      setTasksLoading(true);
      void fetchSessionTasks(sid)
        .then(setRoomTasks)
        .catch(() => setRoomTasks(null))
        .finally(() => setTasksLoading(false));
    },
    [sessionId],
  );

  const refreshCommands = useCallback(
    (overrideId?: string | null) => {
      const sid = overrideId ?? sessionId ?? activeSessionIdRef.current;
      void fetchCommands(sid)
        .then((res) => setSlashCommands(res.commands ?? []))
        .catch(() => setSlashCommands([]));
    },
    [sessionId],
  );

  useEffect(() => {
    refreshCommands();
  }, [refreshCommands]);

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

  const openInspectorPane = useCallback(() => {
    setInspectorOpenState(true);
    setInspectorOpen(true);
  }, []);

  const {
    rightPanelMode,
    setWorkspaceTab,
    setRightPanelMode,
    openWorkTab,
    openReviewTab,
    openPlanTab,
    openTranscriptTab,
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

  useEffect(() => {
    setLastRightPanelMode(rightPanelMode);
  }, [rightPanelMode]);

  const openTasksInspector = useCallback(() => {
    setRightPanelMode("tasks");
    openInspectorPane();
  }, [setRightPanelMode, openInspectorPane]);

  const handleInboxBuildStarted = useCallback(() => {
    openReviewTab();
    refreshSessionMeta();
    if (sessionId) {
      dispatchNotification(
        {
          tier: "P2",
          title: "Build 실행 시작",
          body: "Work 탭에서 진행 상황을 확인하세요.",
          sessionId,
          kind: "human_inbox_build",
          toastAction: { type: "work", focus: "plan" },
        },
        pushMacNotification,
        notifyDesktop,
      );
    }
  }, [openReviewTab, refreshSessionMeta, sessionId, pushMacNotification]);

  const refreshInboxPending = useCallback(async () => {
    if (!sessionId) {
      setInboxPendingCount(0);
      return;
    }
    try {
      const payload = await fetchSessionInbox(sessionId);
      setInboxPendingCount(payload.pending_count ?? 0);
    } catch {
      setInboxPendingCount(0);
    }
  }, [sessionId]);

  const handleInboxResolved = useCallback(() => {
    void refreshInboxPending();
    refreshSessionMeta();
    setDiscussPaused(false);
    setShowInboxPopup(false);
  }, [refreshInboxPending, refreshSessionMeta]);

  const openHumanInbox = useCallback(() => {
    setRightPanelMode("inbox");
  }, [setRightPanelMode]);

  const handleNotificationOpen = useCallback(
    (note: AppNotification) => {
      const action = notificationActionForKind(note.kind);
      if (!action) return;
      if (action.type === "inbox") {
        openHumanInbox();
        return;
      }
      if (action.type === "inspector") {
        setRightPanelMode(action.tab ?? "tasks");
        return;
      }
      if (action.type === "settings") {
        onOpenSettings?.();
        return;
      }
      openWorkTab();
      setWorkFocus(action.focus ?? "plan");
    },
    [onOpenSettings, openHumanInbox, openWorkTab, setRightPanelMode],
  );

  useEffect(() => {
    return subscribeNotificationActions((action) => {
      if (action.type === "inbox") {
        openHumanInbox();
        return;
      }
      if (action.type === "inspector") {
        setRightPanelMode(action.tab ?? "tasks");
        return;
      }
      if (action.type === "settings") {
        onOpenSettings?.();
        return;
      }
      openWorkTab();
      setWorkFocus(action.focus ?? "plan");
    });
  }, [onOpenSettings, openHumanInbox, openWorkTab, setRightPanelMode]);

  const showExecuteQueueStrip =
    tweaks.execQueueDemo === "hidden"
      ? false
      : tweaks.execQueueDemo === "normal" || tweaks.execQueueDemo === "blocked"
        ? true
        : Boolean(sessionId) &&
          !(inspectorOpen && rightPanelMode === "plan") &&
          hasPendingExecution;
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
        toastAction: { type: "work", focus: "execute" },
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
      (Boolean(sessionId) &&
        !(inspectorOpen && rightPanelMode === "plan") &&
        consensusProposal != null));

  const visibleMessages = useMemo(() => {
    if (showHumanSynthesis) {
      return messages.filter(
        (m) => m.role === "you" || Boolean(m.humanSynthesis),
      );
    }
    if (showPeerChannel) return messages;
    return messages.filter((m) => !m.peerChannel);
  }, [messages, showPeerChannel, showHumanSynthesis]);

  function clearRunWatchdog() {
    if (runWatchdogRef.current != null) {
      window.clearTimeout(runWatchdogRef.current);
      runWatchdogRef.current = null;
    }
  }

  function clearLongRunHint() {
    if (longRunHintRef.current != null) {
      window.clearTimeout(longRunHintRef.current);
      longRunHintRef.current = null;
    }
    setLongRunning(false);
  }

  function scheduleLongRunHint() {
    clearLongRunHint();
    if (LONG_RUN_HINT_MS <= 0) return;
    longRunHintRef.current = window.setTimeout(() => {
      setLongRunning(true);
      longRunHintRef.current = null;
    }, LONG_RUN_HINT_MS);
  }

  const handleReleaseRunLock = useCallback(async () => {
    setReleasingLock(true);
    try {
      await releaseRoomRunLock();
      setRunLockStuck(false);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setReleasingLock(false);
    }
  }, []);
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
    if (rightPanelMode !== "plan" || planActionFocusIndex == null) {
      return;
    }
    const index = planActionFocusIndex;
    const timer = window.setTimeout(() => {
      const root = scrollElRef.current;
      const el = root?.querySelector(`[data-plan-action-index="${index}"]`);
      el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      setPlanActionFocusIndex(null);
    }, 80);
    return () => window.clearTimeout(timer);
  }, [rightPanelMode, planActionFocusIndex, scrollElRef]);

  const isNew = !sessionId;
  const notificationUnread = useNotificationUnread();

  const inspectorTasksBadge = useMemo(() => {
    const n = roomTasks?.open_objection_count ?? 0;
    return n > 0 ? n : undefined;
  }, [roomTasks?.open_objection_count]);

  const inspectorInboxBadge = useMemo(() => {
    return inboxPendingCount > 0 ? inboxPendingCount : undefined;
  }, [inboxPendingCount]);

  const titlebarInboxPending = useMemo(() => {
    if (inboxPendingCount > 0) return inboxPendingCount;
    return globalInboxPending > 0 ? globalInboxPending : undefined;
  }, [globalInboxPending, inboxPendingCount]);

  useEffect(() => {
    void refreshInboxPending();
  }, [refreshInboxPending, inboxReloadKey]);

  useEffect(() => {
    let cancelled = false;
    const loadSummary = () => {
      void fetchInboxSummary()
        .then((payload) => {
          if (cancelled) return;
          setGlobalInboxPending(payload.total_pending ?? 0);
        })
        .catch(() => {
          if (!cancelled) setGlobalInboxPending(0);
        });
    };
    loadSummary();
    const timer = window.setInterval(loadSummary, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [sessionId, inboxReloadKey, inboxPendingCount]);

  const toggleInspector = useCallback(() => {
    setInspectorOpenState((current) => {
      const next = !current;
      setInspectorOpen(next);
      return next;
    });
  }, []);

  const setActiveWorkbenchWidth = useCallback((width: number) => {
    setWorkbenchPanelWidthState(width);
  }, []);
  const commitWorkbenchWidth = useCallback((width: number) => {
    setWorkbenchPanelWidthState(width);
    setWorkbenchPanelWidth(width);
  }, []);

  useEffect(() => {
    setGoalText(buildGoalLoopView(session?.run).goal.text ?? "");
    setGoalError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, JSON.stringify(session?.run?.session_goal)]);

  const goalView = useMemo(
    () => buildGoalLoopView(session?.run),
    [session?.run],
  );

  const verifiedLoopView = useMemo(
    () => buildVerifiedLoopView(session?.run),
    [session?.run],
  );

  const planWorkflow = session?.run?.plan_workflow as
    | PlanWorkflowRecord
    | undefined;
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

  const showVerifiedLoop =
    !planWorkflowActive &&
    (turnProfile === "verified" || Boolean(session?.run?.verified_loop));

  const showGoalLoop = !planWorkflowActive && !showVerifiedLoop;

  useEffect(() => {
    setVerifiedEditGoal(verifiedLoopView.proposedGoal);
    setVerifiedEditCriteria(verifiedLoopView.criteria);
    setVerifiedEditPromise(verifiedLoopView.completionPromise || "DONE");
    setVerifiedLoopError(null);
  }, [
    sessionId,
    verifiedLoopView.proposedGoal,
    verifiedLoopView.criteria,
    verifiedLoopView.completionPromise,
  ]);

  const handleGoalSave = useCallback(async () => {
    if (!sessionId || !goalText.trim()) return;
    setGoalBusy(true);
    setGoalError(null);
    try {
      await setSessionGoal(sessionId, { text: goalText.trim() });
      await refreshSessionMeta();
    } catch (e) {
      setGoalError(String(e));
    } finally {
      setGoalBusy(false);
    }
  }, [sessionId, goalText, refreshSessionMeta]);

  const handleGoalCheck = useCallback(async () => {
    if (!sessionId) return;
    setGoalBusy(true);
    setGoalError(null);
    try {
      const res = await checkSessionGoal(sessionId);
      if (res.reason) setGoalError(res.reason);
      await refreshSessionMeta();
    } catch (e) {
      setGoalError(String(e));
    } finally {
      setGoalBusy(false);
    }
  }, [sessionId, refreshSessionMeta]);

  const handleGoalContinueDiscuss = useCallback(
    (prefill: string) => {
      setText(prefill);
      openTranscriptTab();
      focusComposerInput();
    },
    [openTranscriptTab],
  );

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
  const sessionReviewMode = Boolean(
    (session?.run?.last_turn as { review_mode?: boolean } | undefined)
      ?.review_mode,
  );

  useEffect(() => {
    const ready = agents.filter((a) => a.ready).map((a) => a.id);
    if (ready.length === 0) return;
    setSelected((prev) => {
      if (bootstrapAgentIds?.length) {
        const picked = bootstrapAgentIds.filter((id) => ready.includes(id));
        if (picked.length > 0) return picked;
      }
      if (!agentsPickerInitRef.current || prev.length === 0) {
        agentsPickerInitRef.current = true;
        return ready;
      }
      const kept = prev.filter((id) => ready.includes(id));
      return kept.length > 0 ? kept : ready;
    });
  }, [agents, bootstrapAgentIds]);

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

    clearRunWatchdog();

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
    setError(null);
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
    if (isSessionRunActive(sessionId)) return;

    const fp = chatFingerprint(session);
    if (fp !== syncedChatRef.current) {
      syncedChatRef.current = fp;
      hydrateSessionMessages(
        sessionId,
        sessionToMessages(session, sessionReviewMode),
      );
    }
    setPlanMd(session.plan_md || "");
  }, [session, sessionId, sessionReviewMode]);

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
    void cancelRoomRun(primaryId ?? undefined).catch(() => {});
    for (const id of runningIds) {
      updateSessionRun(id, { running: false });
      void pauseMissionLoop(id, { reason: "global_cancel" }).catch(() => {});
    }
    if (primaryId && !runningIds.includes(primaryId)) {
      void pauseMissionLoop(primaryId, { reason: "global_cancel" }).catch(
        () => {},
      );
    }
    clearRunWatchdog();
    runWatchdogRef.current = window.setTimeout(() => {
      for (const id of getRunningSessionIds()) {
        updateSessionRun(id, { runBusy: false });
      }
      runWatchdogRef.current = null;
    }, 45_000);
  }, [sessionId]);

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

  function parseConsensusDryRunProposal(
    ev: Record<string, unknown>,
  ): ConsensusDryRunProposal {
    const recommended = ev.recommended as PlanActionItem | null | undefined;
    return {
      excerpt: typeof ev.excerpt === "string" ? ev.excerpt : undefined,
      summary: typeof ev.summary === "string" ? ev.summary : undefined,
      notice: typeof ev.notice === "string" ? ev.notice : undefined,
      recommended: recommended ?? null,
      has_executable: ev.has_executable === true,
      action_key:
        typeof ev.action_key === "string"
          ? ev.action_key
          : (recommended?.action_key ?? null),
    };
  }

  function notifyConsensusSync(proposal: ConsensusDryRunProposal) {
    const title = consensusDryRunNotifyTitle(proposal.excerpt);
    const body = consensusDryRunNotifyBody(
      proposal.summary,
      proposal.recommended?.what,
    );
    const freeConsensus = turnProfile === "free";
    dispatchNotification(
      {
        tier: "P1",
        title,
        body,
        sessionId: sessionId ?? undefined,
        kind: proposal.recommended ? "consensus_complete" : "plan_sync",
        entityId: proposal.action_key ?? proposal.excerpt,
        toastAction: freeConsensus
          ? { type: "work", focus: "plan" }
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
      const roomMode = mode === "plan" ? "plan" : "discuss";
      const {
        agents,
        agentRounds,
        reviewMode: useReviewMode,
        consensusMode: useConsensusMode,
      } = resolveTurnSend(profile, selected);
      if (agents.length === 0) return;

      const sendText =
        msgText.trim() ||
        (filesToSend.length ? attachmentSendTopic(filesToSend) : "");
      if (!sendText) return;

      const attachmentNames = filesToSend.map((p) => p.file.name);
      const displayBody = msgText.trim();
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
      setError(null);
      setClarifierQuestions(null);
      let userStopped = false;
      let activeSessionId = sessionId;
      let lastSendReceipt: string | undefined;

      try {
        let runFailed = false;
        await runRoom(
          sendText,
          agents,
          (ev) => {
            const t = String(ev.type);
            if (t === "start" && ev.session_id) {
              const boundSessionId = String(ev.session_id);
              activeSessionIdRef.current = boundSessionId;
              activeSessionId = boundSessionId;
              if (runKey === PENDING_KEY || runKey !== boundSessionId) {
                migratePendingSessionRun(boundSessionId);
                runKey = boundSessionId;
              }
              setLiveRunSessionKey(boundSessionId);
              if (!sessionId && !navigatedToSessionRef.current) {
                navigatedToSessionRef.current = true;
                if (onSessionBind) {
                  onSessionBind(boundSessionId);
                } else {
                  void onSessionChange(boundSessionId);
                }
              }
              if (!sessionId && onSessionMetaRefresh) {
                void onSessionMetaRefresh(activeSessionIdRef.current);
              }
              const pendingTemplateId = pendingMissionTemplateRef.current;
              if (!sessionId && pendingTemplateId && boundSessionId) {
                pendingMissionTemplateRef.current = null;
                void applySessionTemplate(boundSessionId, pendingTemplateId)
                  .then((res) => {
                    onBootstrapMissionTemplateApplied?.();
                    if (onSessionMetaRefresh) {
                      void onSessionMetaRefresh(boundSessionId);
                    }
                    if (res.fast_path) {
                      openPlanTab();
                    }
                  })
                  .catch(() => {
                    /* template apply is best-effort; room run continues */
                  });
              }
              if (Array.isArray(ev.attachments) && ev.attachments.length) {
                const saved = ev.attachments as string[];
                patchTurnMessages(runKey, (m) => {
                  for (let i = m.length - 1; i >= 0; i--) {
                    const row = m[i];
                    if (row.role === "you" && row.sent) {
                      const next = [...m];
                      next[i] = { ...row, attachments: saved };
                      return next;
                    }
                  }
                  return m;
                });
              }
            }
            if (t === "run_cancelled") {
              userStopped = true;
            }
            if (t === "agent_round_start" && Number(ev.round) > 1) {
              const round = Number(ev.round);
              updateSessionRun(runKey, { topologyActive: null });
              const rid = `round-divider-${round}`;
              const resolved = resolveTurnSend(profile, selected);
              patchTurnMessages(runKey, (m) => [
                ...m.filter((x) => x.id !== rid),
                {
                  id: rid,
                  role: "system",
                  label: "",
                  body: roundDividerLabel(
                    round,
                    Boolean(ev.review_mode),
                    resolved.consensusMode,
                    Boolean(ev.debate),
                  ),
                  roundDivider: round,
                },
              ]);
            }
            if (t === "consensus_plan_synced" || t === "verified_plan_synced") {
              const excerpt =
                typeof ev.excerpt === "string" ? ev.excerpt : undefined;
              const summary =
                typeof ev.summary === "string" ? ev.summary : undefined;
              const notice =
                typeof ev.notice === "string"
                  ? ev.notice
                  : agreementPlanSyncedLabel(excerpt, summary);
              patchTurnMessages(runKey, (m) => [
                ...m,
                {
                  id: `consensus-sync-${Date.now()}`,
                  role: "system",
                  label: "",
                  body: notice,
                },
              ]);
              refreshSessionMeta();
              setInboxReloadKey((k) => k + 1);
              const partialProposal = {
                excerpt,
                summary,
                notice,
              };
              setConsensusProposal((prev) => ({
                ...partialProposal,
                recommended: prev?.recommended,
                has_executable: prev?.has_executable ?? false,
                action_key: prev?.action_key,
              }));
              notifyConsensusSync(partialProposal);
            }
            if (t === "consensus_dry_run_proposal") {
              const proposal = parseConsensusDryRunProposal(ev);
              refreshSessionMeta();
              setConsensusProposal(proposal);
              notifyConsensusSync(proposal);
            }
            if (
              t === "consensus_plan_sync_failed" ||
              t === "verified_plan_sync_failed"
            ) {
              const excerpt =
                typeof ev.excerpt === "string" ? ev.excerpt : undefined;
              const message =
                typeof ev.message === "string" ? ev.message : undefined;
              patchTurnMessages(runKey, (m) => [
                ...m,
                {
                  id: `consensus-sync-fail-${Date.now()}`,
                  role: "system",
                  label: "",
                  body: agreementPlanSyncFailedLabel(excerpt, message),
                },
              ]);
              notifyConsensusFailure(excerpt, message);
            }
            if (t === "clarifier_prompt" && Array.isArray(ev.questions)) {
              setClarifierQuestions(
                (ev.questions as unknown[])
                  .map((q) => String(q))
                  .filter(Boolean),
              );
              if (ev.interview && typeof ev.interview === "object") {
                setClarifierInterview(
                  ev.interview as {
                    questions?: {
                      id?: string;
                      category?: string;
                      prompt?: string;
                    }[];
                    plan_mode?: boolean;
                  },
                );
              }
            }
            if (t === "consensus_incomplete") {
              patchTurnMessages(runKey, (m) => [
                ...m,
                {
                  id: `consensus-inc-${Date.now()}`,
                  role: "system",
                  label: "",
                  body: consensusIncompleteLabel(
                    typeof ev.message === "string" ? ev.message : undefined,
                  ),
                },
              ]);
            }
            if (t === "agent_start" && ev.agent) {
              const aid = String(ev.agent);
              const round = Number(ev.round ?? 1);
              updateSessionRun(runKey, {
                topologyActive: { agent: aid, round },
              });
              patchTurnMessages(runKey, (m) => [
                ...m.filter((x) => x.id !== `typing-${aid}-r${round}`),
                {
                  id: `typing-${aid}-r${round}`,
                  role: aid as LiveMsg["role"],
                  label: agentLabel(aid),
                  body: "",
                  typing: true,
                  parallelRound: round,
                  activities: [],
                },
              ]);
            }
            if (t === "agent_activity" && ev.agent && ev.text) {
              const aid = String(ev.agent);
              const round = Number(ev.round ?? 1);
              const line = String(ev.text);
              const tid = `typing-${aid}-r${round}`;
              patchTurnMessages(runKey, (m) =>
                m.map((msg) => {
                  if (msg.id !== tid) return msg;
                  const prev = msg.activities ?? [];
                  const next =
                    prev[prev.length - 1] === line
                      ? prev
                      : [...prev, line].slice(-12);
                  return { ...msg, activities: next };
                }),
              );
            }
            if (
              t === "agent_token" &&
              ev.agent &&
              typeof ev.text === "string"
            ) {
              const aid = String(ev.agent);
              const round = Number(ev.round ?? 1);
              const tid = `typing-${aid}-r${round}`;
              const chunk = String(ev.text);
              patchTurnMessages(runKey, (m) =>
                m.map((msg) => {
                  if (msg.id !== tid) return msg;
                  return { ...msg, body: `${msg.body ?? ""}${chunk}` };
                }),
              );
            }
            if (t === "tool_start" && ev.agent) {
              const aid = String(ev.agent);
              const round = Number(ev.round ?? 1);
              const tid = `typing-${aid}-r${round}`;
              const tool = String(ev.tool ?? "tool");
              const argsObj = ev.args as Record<string, unknown> | undefined;
              const target =
                typeof argsObj?.target === "string" ? argsObj.target : "";
              patchTurnMessages(runKey, (m) =>
                m.map((msg) => {
                  if (msg.id !== tid) return msg;
                  const cards = [...(msg.toolCards ?? [])];
                  cards.push({
                    id: `tool-${tool}-${Date.now()}`,
                    tool,
                    args: target || undefined,
                    startedAt: Date.now(),
                  });
                  return { ...msg, toolCards: cards.slice(-16) };
                }),
              );
            }
            if (t === "tool_output" && ev.agent) {
              const aid = String(ev.agent);
              const round = Number(ev.round ?? 1);
              const tid = `typing-${aid}-r${round}`;
              const tool = String(ev.tool ?? "tool");
              const chunk = String(ev.chunk ?? "");
              if (!chunk) return;
              patchTurnMessages(runKey, (m) =>
                m.map((msg) => {
                  if (msg.id !== tid) return msg;
                  const cards = [...(msg.toolCards ?? [])];
                  for (let i = cards.length - 1; i >= 0; i -= 1) {
                    if (cards[i].tool === tool && !cards[i].doneAt) {
                      cards[i] = {
                        ...cards[i],
                        output: `${cards[i].output ?? ""}${chunk}`.slice(-4000),
                      };
                      break;
                    }
                  }
                  return { ...msg, toolCards: cards };
                }),
              );
            }
            if (t === "tool_done" && ev.agent) {
              const aid = String(ev.agent);
              const round = Number(ev.round ?? 1);
              const tid = `typing-${aid}-r${round}`;
              const tool = String(ev.tool ?? "tool");
              patchTurnMessages(runKey, (m) =>
                m.map((msg) => {
                  if (msg.id !== tid) return msg;
                  const cards = [...(msg.toolCards ?? [])];
                  for (let i = cards.length - 1; i >= 0; i -= 1) {
                    if (cards[i].tool === tool && !cards[i].doneAt) {
                      cards[i] = { ...cards[i], doneAt: Date.now() };
                      break;
                    }
                  }
                  return { ...msg, toolCards: cards };
                }),
              );
            }
            if (t === "agent_done" && ev.agent) {
              const aid = String(ev.agent);
              const round = Number(ev.round ?? 1);
              const envelopeParseError = ev.envelope_parse_error === true;
              const envelope = ev.envelope as LiveMsg["envelope"];
              const envelopeLine = formatEnvelopeActivityLine(round, {
                hasAct: Boolean(envelope?.act),
                parseError: envelopeParseError,
              });
              if (envelopeLine) {
                dispatchNotification(
                  {
                    tier: "P2",
                    title: `Envelope · ${aid}`,
                    body: envelopeLine,
                    sessionId: activeSessionId ?? undefined,
                    kind: "envelope_warn",
                    entityId: `${aid}:r${round}`,
                  },
                  pushMacNotification,
                  notifyDesktop,
                );
              }
              updateSessionRun(runKey, (snap) => {
                const n = new Set(snap.topologyDone);
                n.add(`${aid}:${round}`);
                const stillTyping = snap.turnMessages.filter(
                  (m) => m.typing && isReplyWaitRole(m.role),
                );
                const next =
                  stillTyping.length > 0
                    ? {
                        agent: String(stillTyping[0].role),
                        round: stillTyping[0].parallelRound ?? round,
                      }
                    : null;
                return { topologyActive: next, topologyDone: n };
              });
              patchTurnMessages(runKey, (m) => [
                ...m.filter((x) => x.id !== `typing-${aid}-r${round}`),
                {
                  id: `msg-${aid}-r${round}-${Date.now()}`,
                  role: aid as LiveMsg["role"],
                  label: agentLabel(aid),
                  body: String(ev.content ?? "") || "(empty)",
                  parallelRound: round,
                  envelope,
                  envelopeParseError,
                  toolCards: m.find((x) => x.id === `typing-${aid}-r${round}`)
                    ?.toolCards,
                },
              ]);
            }
            if (t === "agent_error" && ev.agent) {
              const aid = String(ev.agent);
              const round = Number(ev.round ?? 1);
              patchTurnMessages(runKey, (m) => [
                ...m.filter((x) => x.id !== `typing-${aid}-r${round}`),
                {
                  id: `err-${aid}-r${round}-${Date.now()}`,
                  role: "system",
                  label: "시스템",
                  body: `[${agentLabel(aid)}] ${ev.message}`,
                },
              ]);
            }
            if (
              (t === "dispatch_start" || t === "dispatch_done") &&
              ev.dispatch_id
            ) {
              const dispatchLine = formatDispatchActivityLine(
                ev as Record<string, unknown>,
              );
              patchTurnMessages(runKey, (m) => [
                ...m,
                {
                  id: `${t}-${String(ev.dispatch_id)}-${Date.now()}`,
                  role: "system",
                  label: "dispatch",
                  body: dispatchLine,
                },
              ]);
            }
            if (t === "hook_event" && ev.event) {
              const sid = activeSessionId ?? undefined;
              const agentName = ev.agent ? agentLabel(String(ev.agent)) : "";
              const eventName = String(ev.event);
              const blocked = ev.blocked === true;
              const feedback =
                typeof ev.feedback === "string" ? ev.feedback.trim() : "";
              const subReason =
                typeof ev.sub_reason === "string" ? ev.sub_reason : "";
              const round = Number(ev.round ?? 1);
              const aid = ev.agent ? String(ev.agent) : "";
              if (aid) {
                const tid = `typing-${aid}-r${round}`;
                const hookLine = formatHookActivityLine({
                  event: eventName,
                  blocked,
                  feedback,
                  sub_reason: subReason,
                });
                patchTurnMessages(runKey, (m) =>
                  m.map((msg) => {
                    if (msg.id !== tid) return msg;
                    const prev = msg.activities ?? [];
                    const next =
                      prev[prev.length - 1] === hookLine
                        ? prev
                        : [...prev, hookLine].slice(-12);
                    return { ...msg, activities: next };
                  }),
                );
              }
              if (blocked || feedback) {
                if (
                  isExecutionRelevantHook(
                    eventName,
                    blocked,
                    feedback || subReason,
                  )
                ) {
                  setWorkHookAlert({
                    event: eventName,
                    body:
                      feedback ||
                      subReason ||
                      (blocked ? "Execution blocked by hook" : eventName),
                    blocked,
                  });
                  openWorkTab();
                }
                dispatchNotification(
                  {
                    tier: blocked ? "P1" : "P2",
                    title: blocked
                      ? `Hook blocked · ${eventName}`
                      : `Hook · ${eventName}`,
                    body:
                      feedback ||
                      (agentName
                        ? `${agentName}${subReason ? ` (${subReason})` : ""}`
                        : subReason),
                    sessionId: sid,
                    kind: blocked ? "hook_blocked" : "hook_warn",
                    entityId: `${eventName}:${String(ev.agent ?? "")}`,
                    forceToast: blocked,
                  },
                  pushMacNotification,
                  notifyDesktop,
                );
              }
            }
            if (t === "plan_workflow_phase" && ev.phase) {
              const phase = String(ev.phase);
              const notice =
                typeof ev.notice === "string" ? ev.notice : undefined;
              patchTurnMessages(runKey, (m) => [
                ...m,
                {
                  id: `plan-workflow-${phase}-${Date.now()}`,
                  role: "system",
                  label: "",
                  body: planWorkflowPhaseTranscriptLine(
                    phase,
                    localeMsg,
                    notice,
                  ),
                },
              ]);
              refreshSessionMeta();
            }
            if (t === "plan_workflow_pending") {
              void refreshSessionMeta();
              dispatchNotification(
                {
                  tier: "P1",
                  title: localeMsg.planWorkflowPendingTitle,
                  body: localeMsg.planWorkflowPendingDetail,
                  sessionId: activeSessionId ?? sessionId ?? undefined,
                  kind: "plan_workflow_pending",
                  toastAction: { type: "inspector", tab: "tasks" },
                  toastActionLabel: localeMsg.planWorkflowPendingOpenTasks,
                },
                pushMacNotification,
                notifyDesktop,
              );
            }
            if (t === "turn_failed") {
              const aid = ev.agent ? String(ev.agent) : "";
              const reason = String(ev.reason ?? "agent_error");
              const detail = ev.message ? `: ${ev.message}` : "";
              patchTurnMessages(runKey, (m) => [
                ...m,
                {
                  id: `turn-failed-${Date.now()}`,
                  role: "system",
                  label: "시스템",
                  body: `[턴 실패${aid ? ` · ${agentLabel(aid)}` : ""}] ${reason}${detail}`,
                },
              ]);
            }
            if (t === "inbox_pause") {
              setDiscussPaused(true);
              setInboxReloadKey((k) => k + 1);
              void refreshInboxPending();
              openHumanInbox();
              setInboxSegment("discuss");
            }
            if (t === "complete" && ev.session_id) {
              activeSessionId = String(ev.session_id);
              if (typeof ev.send_receipt === "string") {
                lastSendReceipt = ev.send_receipt;
              }
              if (ev.inbox_pending === true) {
                setInboxReloadKey((k) => k + 1);
                void fetchSessionInbox(activeSessionId)
                  .then((payload) => {
                    const sid = activeSessionId ?? undefined;
                    const pending = (payload.human_inbox ?? []).filter(
                      (item) => item.status === "pending",
                    );
                    setInboxPendingCount(pending.length);
                    const question = pending.find(
                      (item) => item.kind === "question",
                    );
                    const build = pending.find((item) => item.kind === "build");
                    if (build) {
                      dispatchNotification(
                        {
                          tier: "P1",
                          title: "Build 승인 필요",
                          body: build.summary ?? build.prompt,
                          sessionId: sid,
                          kind: "human_inbox_build",
                          entityId: build.id,
                          toastAction: { type: "work", focus: "plan" },
                        },
                        pushMacNotification,
                        notifyDesktop,
                      );
                    } else if (question) {
                      dispatchNotification(
                        {
                          tier: "P1",
                          title: "에이전트 질문",
                          body: question.prompt,
                          sessionId: sid,
                          kind: "human_inbox_question",
                          entityId: question.id,
                          toastAction: { type: "inbox" },
                        },
                        pushMacNotification,
                        notifyDesktop,
                      );
                    } else if (pending.length > 0) {
                      dispatchNotification(
                        {
                          tier: "P2",
                          title: "Human Inbox",
                          body: `${pending.length}건 대기`,
                          sessionId: sid,
                          kind: "human_inbox",
                          entityId: pending[0]?.id,
                        },
                        pushMacNotification,
                        notifyDesktop,
                      );
                    }
                    const hasBlocking = pending.some(
                      (item) =>
                        item.kind === "question" || item.kind === "build",
                    );
                    if (hasBlocking) {
                      setShowInboxPopup(true);
                    }
                  })
                  .catch(() => {
                    setInboxPendingCount(1);
                  });
              }
              if (ev.verified_loop_pending === true) {
                void refreshSessionMeta();
                const loop = ev.verified_loop as
                  | { proposed?: { goal?: string } }
                  | undefined;
                const goalHint = loop?.proposed?.goal ?? "에이전트 목표 제안";
                dispatchNotification(
                  {
                    tier: "P1",
                    title: "Verified loop 승인",
                    body: goalHint,
                    sessionId: activeSessionId,
                    kind: "verified_loop_pending",
                    toastAction: { type: "inspector", tab: "tasks" },
                    toastActionLabel: "승인하기",
                  },
                  pushMacNotification,
                  notifyDesktop,
                );
              } else if (ev.verified_loop_status === "done") {
                dispatchNotification(
                  {
                    tier: "P1",
                    title: "Oracle VERIFIED",
                    body: "Verified loop 목표 달성",
                    sessionId: activeSessionId,
                    kind: "verified_loop_done",
                    forceToast: true,
                  },
                  pushMacNotification,
                  notifyDesktop,
                );
              } else if (ev.verified_loop_circuit_breaker === true) {
                dispatchNotification(
                  {
                    tier: "P0",
                    title: "Verified loop 중단",
                    body: "Oracle 검증 한도 초과",
                    sessionId: activeSessionId,
                    kind: "verified_loop_failed",
                    forceToast: true,
                  },
                  pushMacNotification,
                  notifyDesktop,
                );
              }
              dispatchNotification(
                {
                  tier: "P2",
                  title: userStopped ? "턴 중지됨" : "턴 완료",
                  body: lastSendReceipt,
                  sessionId: activeSessionId,
                  kind: "turn_complete",
                },
                pushMacNotification,
                notifyDesktop,
              );
            }
            if (t === "run_failed") {
              runFailed = true;
              const msg = String(ev.message ?? "run failed");
              setError(msg);
              setRunLockStuck(true);
              dispatchNotification(
                {
                  tier: "P0",
                  title: "Agent run failed",
                  body: msg,
                  sessionId: sessionId ?? undefined,
                  kind: "run_failed",
                },
                pushMacNotification,
                notifyDesktop,
              );
            }
            if (t === "error") {
              runFailed = true;
              const msg = String(ev.message ?? "run failed");
              setError(
                msg.includes("already in progress")
                  ? "이전 실행이 아직 끝나지 않았습니다. 잠시 후 다시 시도하거나 실행 잠금 해제를 눌러 주세요."
                  : msg,
              );
              if (msg.includes("already in progress")) {
                setRunLockStuck(true);
              }
              dispatchNotification(
                {
                  tier: "P0",
                  title: "Room error",
                  body: msg,
                  sessionId: sessionId ?? undefined,
                  kind: "run_failed",
                },
                pushMacNotification,
                notifyDesktop,
              );
            }
          },
          {
            sessionId: sessionId ?? undefined,
            files: filesToSend.map((p) => p.file),
            mode: roomMode,
            agentRounds,
            permissions,
            reviewMode: useReviewMode,
            consensusMode: useConsensusMode,
            turnProfile: profile,
            researchMode:
              researchMode || normalizeTurnProfile(profile) === "specialist",
            workspaceId: sessionId ? undefined : workspaceId,
            workspacePath:
              sessionId || workspaceId !== CUSTOM_WORKSPACE_ID
                ? undefined
                : (workspacePath ?? undefined),
            agentCapabilities: capabilitiesForApi(agentCapabilities),
            agentThreadBindings: threadBindings,
            sessionTemplate,
          },
        );
        if (runFailed) {
          throw new Error("run failed");
        }
        if (!sessionId) {
          clearStoredAgentThreadBindings();
        }
        if (activeSessionId && !navigatedToSessionRef.current && !sessionId) {
          activeSessionIdRef.current = activeSessionId;
          onSessionChange(activeSessionId);
        }
        if (mode === "plan" && (activeSessionId ?? sessionId)) {
          openPlanTab();
        }
        setSendReceiptRaw(lastSendReceipt);
        setSendReceipt(
          sendReceiptLabel(lastSendReceipt, mode, userStopped, locale),
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
        setError(msg);
        if (msg.includes("already in progress") || msg.includes("not ready")) {
          setRunLockStuck(msg.includes("already in progress"));
        }
      } finally {
        clearRunWatchdog();
        clearLongRunHint();
        finishSessionRun(runKey, activeSessionId ?? undefined);
        const boundSid = activeSessionId ?? sessionId;
        if (boundSid && onSessionMetaRefresh) {
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
      runBusy,
      running,
      synthesizing,
    ],
  );

  const handleVerifiedApprove = useCallback(async () => {
    if (!sessionId || !verifiedEditGoal.trim()) return;
    setVerifiedLoopBusy(true);
    setVerifiedLoopError(null);
    try {
      const approveFn = showPlanApproval ? approvePlan : approveVerifiedLoop;
      const res = await approveFn(sessionId, {
        goal: verifiedEditGoal.trim(),
        completion_promise: verifiedEditPromise.trim() || "DONE",
        criteria: verifiedEditCriteria.trim() || verifiedEditGoal.trim(),
      });
      await refreshSessionMeta();
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
  }, [
    sessionId,
    verifiedEditGoal,
    verifiedEditCriteria,
    verifiedEditPromise,
    refreshSessionMeta,
    executeSend,
    selected,
    showPlanApproval,
  ]);

  const handleVerifiedReject = useCallback(
    async (payload?: { note?: string; target_phase?: string }) => {
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
      setError(null);
      try {
        await runRoom(
          "(plan synthesis)",
          selected,
          (ev) => {
            if (String(ev.type) === "error") {
              setError(String(ev.message ?? "plan synthesis failed"));
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
        setError(String(e));
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
      if (!sessionId) return;
      setCommandHint(null);
      try {
        const res = await runSessionCommand(sessionId, {
          command_id: command.id,
          args,
          confirm,
        });
        if (res.kind === "server") {
          refreshSessionMeta();
          setCommandHint("명령 실행 완료");
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
        setText("");
        void fetchCommands(sessionId)
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
    [sessionId, refreshSessionMeta],
  );

  const runSlashCommand = useCallback(
    async (command: SlashCommandRecord, rawText?: string) => {
      setCommandHint(null);
      if (command.kind === "client") {
        if (command.id === "stop") handleStop();
        if (command.id === "focus-composer") focusComposerInput();
        setText("");
        return;
      }
      if (!sessionId) return;
      const parsed = rawText
        ? matchSlashCommand(rawText, slashCommands)
        : command;
      const target = parsed ?? command;
      const args = rawText ? rawText.replace(/^\/[^\s]+\s*/, "").trim() : "";
      if (
        target.kind === "external" &&
        target.requires_human_confirm !== false
      ) {
        setExternalCommandConfirm({ command: target, args });
        return;
      }
      await executeSlashCommand(target, args);
    },
    [sessionId, slashCommands, executeSlashCommand, handleStop],
  );

  function handleSend() {
    const msg = text.trim();
    if (msg.startsWith("/") && sessionId) {
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
        planAfterSend,
      });
      setPermOpen(true);
      return;
    }
    void executeSend(msg, pendingFiles, roomPermissions(selected));
    setText("");
  }

  const focusPlanAction = (actionIndex: number) => {
    setPlanActionFocusIndex(actionIndex);
    openReviewTab();
  };
  const focusObjection = useCallback(
    (objectionId: string) => {
      setRightPanelMode("tasks");
      setTaskBarFocusObjection({ id: objectionId, nonce: Date.now() });
    },
    [setRightPanelMode],
  );
  const focusTask = useCallback(
    (taskId: string) => {
      openTranscriptTab();
      setRightPanelMode("tasks");
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
    [roomTasks, session?.chat, messages, openTranscriptTab, setRightPanelMode],
  );

  const handleInboxRefClick = useCallback(
    (ref: string) => {
      activateInboxRef(ref, {
        onChatLine: handlePlanRefClick,
        onOpenPlan: () => {
          openWorkTab();
          setWorkFocus("plan");
        },
        onFocusTask: focusTask,
      });
    },
    [focusTask, handlePlanRefClick, openWorkTab],
  );

  const discussRecovery = useMemo(() => {
    const ml = session?.run?.mission_loop as
      | {
          discuss_recovery?: {
            pending?: boolean;
            reason?: string | null;
            action_index?: number | null;
          };
        }
      | undefined;
    return ml?.discuss_recovery ?? null;
  }, [session?.run?.mission_loop]);

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

  const requestComposerPrefill = useCallback(
    (prefill: string) => {
      openTranscriptTab();
      setText(prefill);
      focusComposerInput();
    },
    [openTranscriptTab],
  );
  const executeBusy = planExecute.busy;
  const combinedError = error || planExecute.error;
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

  const readyCount = agents.filter((a) => a.ready).length;
  const agentsBlocked =
    !running && !loading && selected.length === 0 && agents.length >= 0;
  const title = isNew ? "Session" : session?.topic || sessionId || "Session";
  const titleMeta =
    !isNew || selected.length > 0 ? `${selected.length} agents` : undefined;

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
  const taskBarContext = useMemo(
    () => ({
      composerVariant: composerModeVariant,
      turnProfile,
      lastTurnHadConsensus: lastTurnHadConsensusMode(session?.run),
      selectedAgentCount: turnResolved.agents.length,
    }),
    [
      composerModeVariant,
      turnProfile,
      session?.run,
      turnResolved.agents.length,
    ],
  );
  const pendingReplyAgents =
    running && typingAgents.length === 0
      ? turnResolved.agents.map((id) => ({
          id: `pending-${id}`,
          role: id as LiveMsg["role"],
          label: agentLabel(id),
        }))
      : [];

  const runningAgentSlots = useMemo(
    () =>
      deriveRunningAgentSlots(messages, {
        running: running || synthesizing || runBusy,
        expectedAgents: turnResolved.agents,
      }),
    [messages, running, synthesizing, runBusy, turnResolved.agents],
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
        sidebarOpen={_sidebarOpen}
        rightPanelOpen={inspectorOpen}
        rightPanelMode={rightPanelMode}
        locale={locale}
        inboxPendingCount={!isNew ? (titlebarInboxPending ?? 0) : 0}
        panelBadgeCount={
          !isNew
            ? notificationUnread +
              (inspectorTasksBadge ?? 0) +
              (inspectorInboxBadge ?? 0)
            : 0
        }
        running={running || synthesizing || runBusy}
        onToggleSidebar={_onToggleSidebar}
        onToggleRightPanel={toggleInspector}
        onSelectRightPanelMode={setRightPanelMode}
        onOpenInbox={openHumanInbox}
        onOpenSettings={onOpenSettings}
        onStop={handleStop}
      />

      <LiveAgentsStrip
        slots={runningAgentSlots}
        running={running || synthesizing || runBusy}
      />

      <div className="pane-row">
        <div className="pane-main workspace-main">
          <div className="workspace-body">
            <div className="workspace-scroll scroll-y" ref={scrollRef}>
              {!isNew && sessionId ? (
                <div className="taskbar-dock">
                  <RoomTaskBar
                    sessionId={sessionId}
                    payload={roomTasks}
                    context={taskBarContext}
                    loading={tasksLoading}
                    executions={planExecutions}
                    focusObjection={taskBarFocusObjection}
                    humanInboxPendingCount={inboxPendingCount}
                    inboxReloadKey={inboxReloadKey}
                    planRevision={currentPlanRevision}
                    humanInboxDisabled={running || synthesizing || runBusy}
                    onHumanInboxResolved={handleInboxResolved}
                    onHumanInboxBuildStarted={handleInboxBuildStarted}
                    onHumanInboxRefClick={handleInboxRefClick}
                    onOpenInspectorInbox={openHumanInbox}
                    onRefresh={refreshTasks}
                    onFocusPlanAction={focusPlanAction}
                    onFocusTask={focusTask}
                    onRequestComposerPrefill={requestComposerPrefill}
                  />
                </div>
              ) : null}

              {showExecuteQueueStrip && execPendingForBar ? (
                <div className="workspace-event-strip workspace-event-strip--review">
                  <ExecuteQueueBar
                    pending={execPendingForBar}
                    storedActions={
                      (session?.run?.actions as StoredPlanAction[]) ?? []
                    }
                    busy={executeBusy}
                    disabled={running || synthesizing || runBusy}
                    compact
                    onApprove={() => {
                      if (demoExecPending) {
                        pushMacNotification({
                          title: "Execute (demo)",
                          body: "승인 시뮬레이트",
                        });
                        return;
                      }
                      void planExecute.approve();
                    }}
                    onReject={() => {
                      if (demoExecPending) {
                        pushMacNotification({
                          title: "Execute (demo)",
                          body: "거부 시뮬레이트",
                        });
                        return;
                      }
                      void planExecute.reject();
                    }}
                    onOpenPlan={openWorkTab}
                  />
                </div>
              ) : null}

              {showConsensusDryRunGate && consensusForBar ? (
                <div className="workspace-event-strip workspace-event-strip--review">
                  <ConsensusDryRunGateBar
                    proposal={consensusForBar}
                    busy={consensusGateBusy || executeBusy}
                    disabled={running || synthesizing || runBusy}
                    onDryRun={
                      tweaks.consensusGateDemo
                        ? () =>
                            pushMacNotification({
                              title: "Consensus (demo)",
                              body: "Dry-run 시뮬레이트",
                            })
                        : handleConsensusDryRun
                    }
                    onOpenPlan={openWorkTab}
                    onDismiss={
                      tweaks.consensusGateDemo
                        ? () => tweaks.setConsensusGateDemo(false)
                        : dismissConsensusProposal
                    }
                  />
                </div>
              ) : null}

              <div className="transcript transcript--console">
                {!isNew && sessionId ? (
                  <TranscriptViewOptions
                    showHumanSynthesis={showHumanSynthesis}
                    showPeerChannel={showPeerChannel}
                    onHumanSynthesisChange={(on) => {
                      setShowHumanSynthesis(on);
                      setShowHumanSynthesisState(on);
                      if (on) {
                        setShowPeerChannel(false);
                        setShowPeerChannelState(false);
                      }
                    }}
                    onPeerChannelChange={(on) => {
                      setShowPeerChannel(on);
                      setShowPeerChannelState(on);
                    }}
                  />
                ) : null}
                {loading &&
                !isNew &&
                !running &&
                visibleMessages.length === 0 ? (
                  <div className="empty-state">
                    <span className="empty-state__icon" aria-hidden>
                      <svg
                        viewBox="0 0 24 24"
                        width="24"
                        height="24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={1.5}
                      >
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                      </svg>
                    </span>
                    <span className="empty-state__title">
                      {localeMsg.transcriptLoading}
                    </span>
                  </div>
                ) : visibleMessages.length === 0 && !running ? (
                  <div className="empty-state">
                    <span className="empty-state__icon" aria-hidden>
                      <svg
                        viewBox="0 0 24 24"
                        width="24"
                        height="24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={1.5}
                      >
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                      </svg>
                    </span>
                    <span className="empty-state__title">
                      {localeMsg.transcriptEmpty}
                    </span>
                    <span className="empty-state__hint">
                      {localeMsg.transcriptEmptyHint}
                    </span>
                  </div>
                ) : null}
                {visibleMessages.map((m) => {
                  if (m.roundDivider) {
                    const roundLabel =
                      locale === "ko"
                        ? `라운드 ${m.roundDivider}`
                        : `Round ${m.roundDivider}`;
                    return (
                      <div
                        key={m.id}
                        className="round-divider"
                        aria-label={m.body}
                      >
                        {roundLabel}
                      </div>
                    );
                  }
                  if (m.typing && isReplyWaitRole(m.role)) {
                    return (
                      <ReplyWaitingBubble
                        key={m.id}
                        agent={m.role}
                        label={m.label}
                        activities={m.activities}
                        body={m.body}
                      />
                    );
                  }
                  const highlighted = highlightChatLine === m.chatLineIndex;
                  return (
                    <ChatBubble
                      key={m.id}
                      message={m}
                      typing={m.typing}
                      highlighted={highlighted}
                      presentation="console"
                    />
                  );
                })}
                {pendingReplyAgents.map((a) => (
                  <ReplyWaitingBubble
                    key={a.id}
                    agent={a.role}
                    label={a.label}
                    activities={[]}
                  />
                ))}
              </div>

              {transcriptActive && (
                <ScrollToBottomButton
                  visible={showJumpButton || tweaks.forceScrollButton}
                  onClick={scrollToBottom}
                />
              )}
            </div>

            {isNew || transcriptActive ? (
              <>
                {tweaks.preflightDemo ? (
                  <ComposerPreflightBar
                    agents={DEMO_PREFLIGHT_AGENTS}
                    selected={["cursor"]}
                  />
                ) : (
                  <>
                    <ReadinessComposerBar readiness={readiness} />
                    <ComposerPreflightBar
                      agents={healthAgents}
                      selected={selected}
                    />
                  </>
                )}
                <div className="composer-wrap">
                  {clarifierQuestions && clarifierQuestions.length > 0 ? (
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

                  {combinedError ? (
                    <div
                      className="error-banner"
                      role="alert"
                      aria-label="룸 오류"
                    >
                      {combinedError}
                    </div>
                  ) : null}

                  {agentsBlocked && !combinedError ? (
                    <div
                      className="error-banner"
                      role="status"
                      aria-label="에이전트 준비 상태"
                    >
                      {agents.length === 0
                        ? "API(8765)에 연결할 수 없습니다. Tauri 앱을 완전히 종료한 뒤 make tauri-dev로 다시 시작하세요."
                        : `준비된 에이전트가 없습니다 (${readyCount}/3). cursor/codex/claude 로그인을 확인하세요.`}
                    </div>
                  ) : null}

                  {showPlanWorkflowComposerHint && planWorkflow ? (
                    <PlanWorkflowBanner
                      workflow={planWorkflow}
                      variant="compact"
                      onOpenTasks={openTasksInspector}
                    />
                  ) : null}

                  {showPlanWorkflowBanner && planWorkflow ? (
                    <PlanWorkflowBanner
                      workflow={planWorkflow}
                      inboxPendingCount={inboxPendingCount}
                      running={running || runBusy || synthesizing}
                      hideInboxButton={humanDecisionBannerVisible}
                      onOpenInbox={openHumanInbox}
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

                  {discussRecovery?.pending ? (
                    <DiscussRecoveryBanner
                      recovery={discussRecovery}
                      busy={discussRecoveryBusy}
                      onRunRecovery={() => void handleDiscussRecoveryRun()}
                      onOpenDiscussInbox={() => {
                        setInboxSegment("discuss");
                        openHumanInbox();
                      }}
                    />
                  ) : null}

                  {!isNew && sessionId ? (
                    <HumanDecisionBanner
                      sessionId={sessionId}
                      reloadKey={inboxReloadKey}
                      discussPaused={discussPaused}
                      onVisibleChange={setHumanDecisionBannerVisible}
                      onOpenInbox={() => {
                        setInboxSegment("discuss");
                        openHumanInbox();
                      }}
                    />
                  ) : null}

                  {showInboxPopup && sessionId && inboxPendingCount > 0 ? (
                    <HumanInboxPanel
                      sessionId={sessionId}
                      reloadKey={inboxReloadKey}
                      planRevision={currentPlanRevision}
                      onResolved={handleInboxResolved}
                      onBuildStarted={handleInboxBuildStarted}
                      disabled={running || synthesizing || runBusy}
                      presentation="popup"
                      onDismiss={() => setShowInboxPopup(false)}
                      onOpenInbox={() => {
                        setShowInboxPopup(false);
                        openHumanInbox();
                      }}
                      onRefClick={handleInboxRefClick}
                    />
                  ) : null}

                  {inboxPendingCount > 0 ? (
                    <button
                      type="button"
                      className="composer-inbox-pending"
                      onClick={openHumanInbox}
                    >
                      Human Inbox 대기 ({inboxPendingCount})
                    </button>
                  ) : null}

                  <ChatComposer
                    className={
                      [
                        turnProfile === "review"
                          ? "composer--review"
                          : undefined,
                        turnProfile === "free" ? "composer--free" : undefined,
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
                    modeChip={modeChipCopy.label}
                    modeChipVariant={composerModeVariant}
                    modeChipHint={modeChipCopy.hint}
                    running={running}
                    onStop={handleStop}
                    files={pendingFiles}
                    onFilesAdd={addFiles}
                    onFileRemove={(id) =>
                      setPendingFiles((f) => f.filter((x) => x.id !== id))
                    }
                    turnProfile={turnProfile}
                    onTurnProfileChange={changeTurnProfile}
                    planAfterSend={planAfterSend}
                    onPlanAfterSendChange={changePlanAfterSend}
                    planToggleDisabled={planWorkflowAwaitingApproval}
                    objectionNotice={composerObjectionNotice}
                    onFocusObjection={focusObjection}
                    turnHint={composerTurnHintLine}
                    locale={locale}
                    sessionId={sessionId}
                  />

                  {commandHint ? (
                    <p className="composer-command-hint" role="status">
                      {commandHint}
                    </p>
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
                    pendingSend.planAfterSend ? "plan" : "discuss",
                    pendingSend.turnProfile,
                  );
                  setPendingSend(null);
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
            {rightPanelMode === "tasks" ? (
              <>
                <HumanGatePanel>
                  {sessionId && showPlanWorkflowBanner && planWorkflow ? (
                    <PlanWorkflowBanner
                      workflow={planWorkflow}
                      inboxPendingCount={inboxPendingCount}
                      running={running || runBusy || synthesizing}
                      hideInboxButton={humanDecisionBannerVisible}
                      onOpenInbox={openHumanInbox}
                    />
                  ) : null}
                  {sessionId && showPlanApproval ? (
                    <PlanApprovalPanel
                      view={verifiedLoopView}
                      planMd={session?.plan_md ?? ""}
                      phase={planWorkflow?.phase ?? "HUMAN_PENDING"}
                      workflowNotice={planWorkflow?.notice}
                      planGate={planWorkflow?.last_plan_gate ?? null}
                      objections={roomTasks?.open_objections ?? []}
                      busy={verifiedLoopBusy || running || runBusy}
                      error={verifiedLoopError}
                      editGoal={verifiedEditGoal}
                      editCriteria={verifiedEditCriteria}
                      editPromise={verifiedEditPromise}
                      onEditGoalChange={setVerifiedEditGoal}
                      onEditCriteriaChange={setVerifiedEditCriteria}
                      onEditPromiseChange={setVerifiedEditPromise}
                      onFocusObjection={focusObjection}
                      onApprove={() => void handleVerifiedApprove()}
                      onReject={(payload) => void handleVerifiedReject(payload)}
                    />
                  ) : sessionId && showVerifiedLoop ? (
                    <VerifiedLoopBanner
                      view={verifiedLoopView}
                      busy={verifiedLoopBusy || running || runBusy}
                      error={verifiedLoopError}
                      editGoal={verifiedEditGoal}
                      editCriteria={verifiedEditCriteria}
                      editPromise={verifiedEditPromise}
                      onEditGoalChange={setVerifiedEditGoal}
                      onEditCriteriaChange={setVerifiedEditCriteria}
                      onEditPromiseChange={setVerifiedEditPromise}
                      onApprove={() => void handleVerifiedApprove()}
                      onReject={() => void handleVerifiedReject()}
                    />
                  ) : sessionId && showGoalLoop ? (
                    <GoalLoopBanner
                      goalView={goalView}
                      goalText={goalText}
                      goalBusy={goalBusy}
                      goalError={goalError}
                      onGoalTextChange={setGoalText}
                      onSave={() => void handleGoalSave()}
                      onCheck={() => void handleGoalCheck()}
                      onContinueDiscuss={handleGoalContinueDiscuss}
                    />
                  ) : null}
                </HumanGatePanel>
                <ContextTasksPanel
                  sessionId={sessionId ?? ""}
                  tasks={[
                    ...(roomTasks?.tasks ?? []),
                    ...(roomTasks?.claimable ?? []),
                  ]}
                  objections={roomTasks?.objections ?? []}
                  disabled={running || synthesizing || runBusy}
                  onChanged={refreshTasks}
                  onFocusTask={focusTask}
                  onFocusObjection={focusObjection}
                />
              </>
            ) : null}
            {rightPanelMode === "inbox" ? (
              <>
                <div
                  className="ctx-segmented"
                  role="tablist"
                  aria-label="Inbox filter"
                >
                  {(
                    [
                      "all",
                      "discuss",
                      "activity",
                      "questions",
                      "build",
                      "skills",
                    ] as const
                  ).map((segment) => (
                    <button
                      key={segment}
                      type="button"
                      role="tab"
                      aria-selected={inboxSegment === segment}
                      className={inboxSegment === segment ? "is-active" : ""}
                      onClick={() => setInboxSegment(segment)}
                    >
                      {segment === "all"
                        ? localeMsg.inboxAll
                        : segment === "discuss"
                          ? localeMsg.inboxDiscuss
                          : segment === "activity"
                            ? localeMsg.inboxActivity
                            : segment === "questions"
                              ? localeMsg.inboxQuestions
                              : segment === "build"
                                ? localeMsg.inboxBuild
                                : localeMsg.inboxSkills}
                    </button>
                  ))}
                </div>
                {inboxSegment === "discuss" ? (
                  <DiscussInboxPanel
                    sessionId={sessionId}
                    reloadKey={inboxReloadKey}
                    planRevision={currentPlanRevision}
                    discussPaused={discussPaused}
                    discussRecovery={discussRecovery}
                    discussRecoveryBusy={discussRecoveryBusy}
                    onRunDiscussRecovery={() => void handleDiscussRecoveryRun()}
                    onResolved={handleInboxResolved}
                    onBuildStarted={handleInboxBuildStarted}
                    disabled={running || synthesizing || runBusy}
                    onOpenInbox={openHumanInbox}
                    onRefClick={handleInboxRefClick}
                  />
                ) : null}
                {inboxSegment !== "activity" && inboxSegment !== "discuss" ? (
                  <HumanInboxPanel
                    sessionId={sessionId}
                    reloadKey={inboxReloadKey}
                    planRevision={currentPlanRevision}
                    onResolved={handleInboxResolved}
                    onBuildStarted={handleInboxBuildStarted}
                    disabled={running || synthesizing || runBusy}
                    presentation="inspector"
                    onRefClick={handleInboxRefClick}
                    kindFilter={
                      inboxSegment === "questions"
                        ? "question"
                        : inboxSegment === "build"
                          ? "build"
                          : inboxSegment === "skills"
                            ? "skill_draft"
                            : undefined
                    }
                  />
                ) : null}
                {inboxSegment === "all" || inboxSegment === "activity" ? (
                  <NotificationCenter onOpen={handleNotificationOpen} />
                ) : null}
              </>
            ) : null}
            {rightPanelMode === "plan" && sessionId ? (
              <WorkToolPanel
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
                onSynthesizeNow={handleSynthesizeNow}
                onPlanRefClick={handlePlanRefClick}
                onFocusTask={focusTask}
                onFocusObjection={focusObjection}
                onSessionUpdated={refreshSessionMeta}
                roomTasks={roomTasks}
                cursorReady={agents.some((a) => a.id === "cursor" && a.ready)}
                workHookAlert={workHookAlert}
                onDismissWorkHookAlert={() => setWorkHookAlert(null)}
              />
            ) : null}
            {rightPanelMode === "background" && sessionId ? (
              <BackgroundTasksPanel sessionId={sessionId} />
            ) : null}
            {rightPanelMode === "diff" ? (
              <DiffToolPanel executions={planExecutions} />
            ) : null}
            {rightPanelMode === "files" && sessionId ? (
              <WorkspaceFilesPanel sessionId={sessionId} />
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
