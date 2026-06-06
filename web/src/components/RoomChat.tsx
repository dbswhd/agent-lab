import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AgentOption, PlanActionItem, SessionDetail } from "../api/client";
import {
  cancelRoomRun,
  checkSessionGoal,
  fetchCommands,
  matchSlashCommand,
  releaseRoomRunLock,
  runRoom,
  runSessionCommand,
  setSessionGoal,
  type AgentHealthRow,
  type GoalLoopRecord,
  type SessionGoalRecord,
  type SlashCommandRecord,
} from "../api/client";
import {
  agentLabel,
  chatLineToMessage,
  parseTranscript,
  topicAsUserMessage,
} from "../utils/transcript";
import { AgentPicker } from "./AgentPicker";
import { WorkspaceTabBar } from "./WorkspaceTabBar";
import { InspectorPane } from "./InspectorPane";
import {
  CommandPalette,
  workspacePaletteActions,
} from "./CommandPalette";
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
import {
  getInspectorOpen,
  getInspectorWidth,
  setInspectorOpen,
  setInspectorWidth,
} from "../utils/inspectorPanePrefs";
import {
  getShowHumanSynthesis,
  setShowHumanSynthesis,
} from "../utils/transcriptViewPrefs";
import {
  ChatBubble,
  isReplyWaitRole,
  ReplyWaitingBubble,
} from "./ChatBubble";
import { HumanInboxPanel } from "./HumanInboxPanel";
import { ChatComposer, type PendingFile } from "./ChatComposer";
import { ChatPaneBody } from "./ChatPaneBody";
import { ChatToolbar } from "./ChatToolbar";
import { ContextSidebarToggle } from "./ContextSidebarToggle";
import { NotificationCenter, useNotificationUnread } from "./NotificationCenter";
import { QuickSettingsPanel } from "./QuickSettingsPanel";
import { WorkPanel } from "./WorkPanel";
import { AgentPermissionAlert } from "./AgentPermissionAlert";
import { useMacNotifications } from "./MacNotificationHost";
import type { AgentPermissions } from "../utils/agentPermissions";
import {
  roomPermissions,
} from "../utils/agentPermissions";
import {
  agreementPlanSyncedLabel,
  agreementPlanSyncFailedLabel,
  consensusDryRunNotifyBody,
  consensusDryRunNotifyTitle,
} from "../utils/consensusAgreement";
import { dispatchNotification } from "../utils/pushNotification";
import { notifyDesktop } from "../utils/desktopNotify";
import { buildPlanMetaView } from "../utils/planMeta";
import { analyzePlanRefWarnings } from "../utils/planRefWarnings";
import {
  consensusIncompleteLabel,
  roundDividerLabel,
} from "../utils/roundTopology";
import {
  getEfficiencyMode,
  setEfficiencyMode,
} from "../utils/efficiencyPrefs";
import {
  normalizeTurnProfile,
  resolveTurnSend,
  setTurnProfile,
  type ComposerTurnProfile,
} from "../utils/turnProfile";
import { estimateTurnCost } from "../utils/turnCostEstimate";
import { formatRoomModelLine } from "../utils/roomModels";
import { TurnRunPanel } from "./TurnRunPanel";
import { ExecuteQueueBar } from "./ExecuteQueueBar";
import { ConsensusDryRunGateBar } from "./ConsensusDryRunGateBar";
import type { ConsensusDryRunProposal } from "./ConsensusDryRunGateBar";
import {
  getPlanAfterSend,
  setPlanAfterSend,
  setTurnStrategy,
  getTurnStrategy,
  type ComposeMode,
} from "../utils/composeMode";
import { usePlanExecute } from "../hooks/usePlanExecute";
import {
  type StoredPlanAction,
} from "../utils/planExecuteHistory";
import { SessionSetupBar } from "./SessionSetupBar";
import { AgentSessionSettings } from "./AgentSessionSettings";
import {
  fetchSessionAgentCapabilities,
  fetchSessionSetupOptions,
  fetchSessionTasks,
  patchSessionAgentCapabilities,
  type PlanExecutionRecord,
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
  getStoredWorkspaceId,
  getStoredWorkspacePath,
  sessionSetupSummary,
  setStoredWorkspaceId,
  setStoredWorkspacePath,
} from "../utils/sessionSetup";
import { pickWorkspaceFolder } from "../utils/pickWorkspaceFolder";
import {
  sendReceiptLabel,
  shouldShowSendReceiptOnChatTab,
} from "../utils/sendReceipt";
import { ComposerPreflightBar } from "./ComposerPreflightBar";
import {
  ScrollToBottomButton,
  useMessagesScroll,
  useScrollToTop,
} from "./ScrollToBottomButton";

const LONG_RUN_HINT_MS = Number(
  import.meta.env.VITE_ROOM_LONG_RUN_HINT_MS || "180000",
);

type GoalLoopView = {
  goal: SessionGoalRecord;
  loop: GoalLoopRecord;
};

function goalLoopView(run: Record<string, unknown> | undefined): GoalLoopView {
  const goal =
    run?.session_goal && typeof run.session_goal === "object"
      ? (run.session_goal as SessionGoalRecord)
      : {};
  const loop =
    run?.goal_loop && typeof run.goal_loop === "object"
      ? (run.goal_loop as GoalLoopRecord)
      : {};
  return { goal, loop };
}

type Props = {
  agents: AgentOption[];
  healthAgents?: AgentHealthRow[];
  sessionId: string | null;
  session: SessionDetail | null;
  loading?: boolean;
  onSessionChange: (sessionId: string) => void | Promise<void>;
  /** run.json / plan.md only — must not reset chat messages */
  onSessionMetaRefresh?: (sessionId: string) => void | Promise<void>;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  onOpenSettings?: () => void;
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
      if (line.role === "agent" && pr > 1 && pr > lastRound) {
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
  onSessionMetaRefresh,
  sidebarOpen,
  onToggleSidebar,
  onOpenSettings,
}: Props) {
  const { push: pushMacNotification } = useMacNotifications();
  const [selected, setSelected] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const runSessionKey = sessionId ?? PENDING_KEY;
  const {
    messages,
    turnMessages,
    running,
    runBusy,
    synthesizing,
    topologyDone,
    topologyActive,
    setSynthesizing,
  } = useSessionRunState(runSessionKey);
  const [error, setError] = useState<string | null>(null);
  const [planActionFocusIndex, setPlanActionFocusIndex] = useState<
    number | null
  >(null);
  const [showPeerChannel, setShowPeerChannel] = useState(false);
  const [showHumanSynthesis, setShowHumanSynthesisState] = useState(
    getShowHumanSynthesis,
  );
  const [viewOptionsOpen, setViewOptionsOpen] = useState(false);
  const [inspectorOpen, setInspectorOpenState] = useState(getInspectorOpen);
  const [inspectorWidth, setInspectorWidthState] = useState(getInspectorWidth);
  const [roomTasks, setRoomTasks] = useState<RoomTasksPayload | null>(null);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [planMd, setPlanMd] = useState("");
  const [permOpen, setPermOpen] = useState(false);
  const [turnProfile, setTurnProfileState] = useState<ComposerTurnProfile>(
    getTurnStrategy,
  );
  const [planAfterSend, setPlanAfterSendState] = useState(getPlanAfterSend);
  const composeMode: ComposeMode = planAfterSend ? "plan" : "discuss";
  const [efficiencyOn, setEfficiencyOnState] = useState(getEfficiencyMode);
  const [researchMode, setResearchModeState] = useState(() => {
    try {
      return localStorage.getItem("agent-lab-research-mode") === "1";
    } catch {
      return false;
    }
  });
  const composerModeVariant = useMemo((): "discuss" | "plan" | "consensus" => {
    const profile = resolveTurnSend(turnProfile, selected, efficiencyOn);
    if (profile.consensusMode) return "consensus";
    if (planAfterSend) return "plan";
    return "discuss";
  }, [turnProfile, selected, efficiencyOn, planAfterSend]);
  const turnCost = useMemo(
    () => estimateTurnCost(turnProfile, selected, { efficiencyOn }),
    [turnProfile, selected, efficiencyOn],
  );
  const [pendingSend, setPendingSend] = useState<{
    text: string;
    files: PendingFile[];
    turnProfile: ComposerTurnProfile;
    planAfterSend: boolean;
    efficiencyOn: boolean;
  } | null>(null);
  const [highlightChatLine, setHighlightChatLine] = useState<number | null>(
    null,
  );
  const [taskBarFocusObjection, setTaskBarFocusObjection] = useState<{
    id: string;
    nonce: number;
  } | null>(null);
  const highlightTimerRef = useRef<number | null>(null);
  const [sendReceipt, setSendReceipt] = useState<string | null>(null);
  const [inboxPendingChip, setInboxPendingChip] = useState(false);
  const [inboxReloadKey, setInboxReloadKey] = useState(0);
  const [inboxPopupDismissed, setInboxPopupDismissed] = useState(false);
  const sendReceiptTimerRef = useRef<number | null>(null);
  const [clarifierQuestions, setClarifierQuestions] = useState<string[] | null>(
    null,
  );
  const [goalText, setGoalText] = useState("");
  const [goalBusy, setGoalBusy] = useState(false);
  const [goalError, setGoalError] = useState<string | null>(null);
  const [slashCommands, setSlashCommands] = useState<SlashCommandRecord[]>([]);
  const [commandHint, setCommandHint] = useState<string | null>(null);
  const runWatchdogRef = useRef<number | null>(null);
  const syncedChatRef = useRef("");
  const [setupWorkspaces, setSetupWorkspaces] = useState<WorkspacePreset[]>([]);
  const [workspaceId, setWorkspaceIdState] = useState(getStoredWorkspaceId);
  const [workspacePath, setWorkspacePathState] = useState<string | null>(
    getStoredWorkspacePath,
  );
  const [consensusProposal, setConsensusProposal] =
    useState<ConsensusDryRunProposal | null>(null);
  const [consensusGateBusy, setConsensusGateBusy] = useState(false);
  const [longRunning, setLongRunning] = useState(false);
  const [runLockStuck, setRunLockStuck] = useState(false);
  const [releasingLock, setReleasingLock] = useState(false);
  const longRunHintRef = useRef<number | null>(null);
  const [agentCapabilities, setAgentCapabilities] = useState<AgentCapabilitiesMap>(
    () => cloneCapabilities(DEFAULT_AGENT_CAPABILITIES),
  );
  const [resolvedAgentCwd, setResolvedAgentCwd] = useState<
    Record<string, string>
  >({});
  const [agentCapsBusy, setAgentCapsBusy] = useState(false);
  const [agentCapsHint, setAgentCapsHint] = useState<string | null>(null);
  const activeSessionIdRef = useRef<string | null>(sessionId);
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

  async function browseWorkspaceFolder() {
    const picked = await pickWorkspaceFolder(workspacePath);
    if (!picked) return;
    setWorkspaceId(CUSTOM_WORKSPACE_ID, picked);
  }

  useEffect(() => {
    fetchSessionSetupOptions()
      .then((opts) => {
        setSetupWorkspaces(opts.workspaces);
        const wsIds = new Set(opts.workspaces.map((w) => w.id));
        if (
          workspaceId !== CUSTOM_WORKSPACE_ID &&
          !wsIds.has(workspaceId)
        ) {
          setWorkspaceId(opts.defaults.workspace_id, null);
        }
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps -- hydrate once; stored ids validated against API
  }, []);

  useEffect(() => {
    activeSessionIdRef.current = sessionId;
  }, [sessionId]);

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
    void fetchSessionAgentCapabilities(sessionId, perms as Record<string, unknown>)
      .then((r) => {
        if (!raw && r.agent_capabilities) {
          setAgentCapabilities(parseAgentCapabilities(r.agent_capabilities));
        }
        setResolvedAgentCwd(r.resolved_cwd ?? {});
      })
      .catch(() => {});
  }, [sessionId, selected, session?.run?.agent_capabilities]);

  const goalView = useMemo(() => goalLoopView(session?.run), [session?.run]);
  useEffect(() => {
    setGoalText(goalView.goal.text ?? "");
    setGoalError(null);
  }, [sessionId, goalView.goal.text]);

  function effectiveSessionId(): string | null {
    return sessionId ?? activeSessionIdRef.current;
  }

  function handleAgentCapabilitiesChange(caps: AgentCapabilitiesMap) {
    agentCapsDirtyRef.current = true;
    setAgentCapabilities(caps);
    setAgentCapsHint(null);
  }

  function changeTurnProfile(profile: ComposerTurnProfile) {
    setTurnProfileState(profile);
    setTurnStrategy(profile);
    setTurnProfile(profile);
  }

  function changePlanAfterSend(on: boolean) {
    setPlanAfterSendState(on);
    setPlanAfterSend(on);
  }

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

  const saveSessionGoal = useCallback(async () => {
    const text = goalText.trim();
    if (!sessionId || !text) return;
    setGoalBusy(true);
    setGoalError(null);
    try {
      await setSessionGoal(sessionId, { text });
      refreshSessionMeta();
    } catch (e) {
      setGoalError(e instanceof Error ? e.message : "목표 저장 실패");
    } finally {
      setGoalBusy(false);
    }
  }, [sessionId, goalText]);

  const runGoalCheck = useCallback(async () => {
    if (!sessionId) return;
    setGoalBusy(true);
    setGoalError(null);
    try {
      await checkSessionGoal(sessionId);
      refreshSessionMeta();
    } catch (e) {
      setGoalError(e instanceof Error ? e.message : "목표 확인 실패");
    } finally {
      setGoalBusy(false);
    }
  }, [sessionId]);

  const saveAgentCapabilities = useCallback(async () => {
    if (!sessionId) return;
    setAgentCapsBusy(true);
    setAgentCapsHint(null);
    try {
      const res = await patchSessionAgentCapabilities(
        sessionId,
        capabilitiesForApi(agentCapabilities),
      );
      setResolvedAgentCwd(res.resolved_cwd ?? {});
      setAgentCapsHint("저장됨");
      agentCapsDirtyRef.current = false;
      refreshSessionMeta();
    } catch (e) {
      setAgentCapsHint(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setAgentCapsBusy(false);
    }
  }, [sessionId, agentCapabilities, refreshSessionMeta]);

  useEffect(() => {
    refreshTasks();
  }, [refreshTasks, session?.run, session?.chat?.length]);

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

  const {
    workspaceTab,
    inspectorTab,
    setWorkspaceTab,
    setInspectorTab,
    openWorkTab,
    openReviewTab,
    openPlanTab,
    openTranscriptTab,
  } = useWorkspaceTabs({
    sessionKey: sessionId ?? "new",
    isNew: !sessionId,
    autoContext: {
      running,
      hasPendingExecution,
      hasDryRunDiff,
      planMd,
      hasBlocker,
    },
  });

  const handleInboxBuildStarted = useCallback(() => {
    openReviewTab();
    refreshSessionMeta();
  }, [openReviewTab, refreshSessionMeta]);

  const handleInboxResolved = useCallback(() => {
    setInboxPendingChip(false);
    setInboxPopupDismissed(false);
    refreshSessionMeta();
  }, [refreshSessionMeta]);

  const openHumanInbox = useCallback(() => {
    setInspectorOpenState(true);
    setInspectorOpen(true);
    setInspectorTab("tasks");
  }, [setInspectorTab]);

  const openNotificationTarget = useCallback(
    (notification: { kind: string }) => {
      if (notification.kind === "human_inbox") {
        openHumanInbox();
        return;
      }
      if (
        notification.kind === "dry_run" ||
        notification.kind === "plan_sync" ||
        notification.kind === "plan_sync_fail"
      ) {
        openWorkTab();
        return;
      }
      if (notification.kind === "bridge" || notification.kind === "diagnostics") {
        onOpenSettings?.();
        return;
      }
      setInspectorTab("activity");
    },
    [openHumanInbox, openWorkTab, onOpenSettings, setInspectorTab],
  );

  const showExecuteQueueStrip =
    Boolean(sessionId) &&
    workspaceTab !== "work" &&
    hasPendingExecution;
  const showConsensusDryRunGate =
    Boolean(sessionId) &&
    workspaceTab !== "work" &&
    !showExecuteQueueStrip &&
    consensusProposal != null;

  const visibleMessages = useMemo(() => {
    if (showHumanSynthesis) {
      return messages.filter(
        (m) => m.role === "you" || Boolean(m.humanSynthesis),
      );
    }
    if (showPeerChannel) return messages;
    return messages.filter((m) => !m.peerChannel);
  }, [messages, showPeerChannel, showHumanSynthesis]);

  const hiddenPeerCount = messages.filter((m) => m.peerChannel).length;
  const hiddenAgentCount = showHumanSynthesis
    ? messages.filter((m) => m.role !== "you" && !m.humanSynthesis).length
    : 0;

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
  const transcriptActive =
    workspaceTab === "transcript" || (workspaceTab === "work" && !planMd);
  const typingAgents = messages.filter(
    (m) => m.typing && isReplyWaitRole(m.role),
  );
  const pendingReplyCount =
    running && workspaceTab === "transcript" && typingAgents.length === 0
      ? resolveTurnSend(turnProfile, selected, efficiencyOn).agents.length
      : 0;
  const { scrollRef, scrollElRef, showJumpButton, scrollToBottom } = useMessagesScroll(
    [messages, running, pendingReplyCount, selected.join(",")],
    transcriptActive,
    `${sessionId ?? "new"}:chat`,
  );
  const { scrollRef: workScrollRef, scrollElRef: workScrollElRef } =
    useScrollToTop(
      workspaceTab === "work" && Boolean(sessionId),
      `${sessionId ?? "new"}:work`,
    );

  const planExecutions = useMemo(
    () =>
      (session?.run?.executions as PlanExecutionRecord[] | undefined) ?? [],
    [session?.run?.executions],
  );

  useEffect(() => {
    if (workspaceTab !== "work" || planActionFocusIndex == null) {
      return;
    }
    const index = planActionFocusIndex;
    const timer = window.setTimeout(() => {
      const root = workScrollElRef.current;
      const el = root?.querySelector(
        `[data-plan-action-index="${index}"]`,
      );
      el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      setPlanActionFocusIndex(null);
    }, 80);
    return () => window.clearTimeout(timer);
  }, [workspaceTab, planActionFocusIndex, workScrollElRef]);

  const isNew = !sessionId;
  const notificationUnread = useNotificationUnread();

  const toggleInspector = useCallback(() => {
    setInspectorOpenState((current) => {
      const next = !current;
      setInspectorOpen(next);
      return next;
    });
  }, []);

  const commitInspectorWidth = useCallback((width: number) => {
    setInspectorWidthState(width);
    setInspectorWidth(width);
  }, []);

  useEffect(() => {
    if (isNew) return;
    function onKeyDown(event: KeyboardEvent) {
      if (!event.metaKey || event.altKey) return;
      if (event.ctrlKey && event.key.toLowerCase() === "i") {
        event.preventDefault();
        toggleInspector();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isNew, toggleInspector]);

  const waitingForSession = Boolean(sessionId && !session && loading);
  const composerInputLocked = waitingForSession;
  const preflightBlocked = selected.some((id) => {
    const row = healthAgents.find((a) => a.id === id);
    return Boolean(row && !row.ready);
  });
  const customWorkspaceBlocked =
    isNew &&
    workspaceId === CUSTOM_WORKSPACE_ID &&
    !workspacePath?.trim();
  const composerSendLocked =
    runBusy ||
    running ||
    synthesizing ||
    (loading && waitingForSession) ||
    selected.length === 0 ||
    preflightBlocked ||
    customWorkspaceBlocked ||
    (!text.trim() && pendingFiles.length === 0);
  const sessionReviewMode = Boolean(
    (session?.run?.last_turn as { review_mode?: boolean } | undefined)
      ?.review_mode,
  );

  useEffect(() => {
    const ready = agents.filter((a) => a.ready).map((a) => a.id);
    if (ready.length === 0) return;
    setSelected((prev) => {
      if (!agentsPickerInitRef.current || prev.length === 0) {
        agentsPickerInitRef.current = true;
        return ready;
      }
      const kept = prev.filter((id) => ready.includes(id));
      return kept.length > 0 ? kept : ready;
    });
  }, [agents]);

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
    hydrateSessionMessages(PENDING_KEY, []);
    setPlanMd("");
  }, [sessionId]);

  function toggleAgent(id: string) {
    setSelected((s) =>
      s.includes(id) ? s.filter((x) => x !== id) : [...s, id],
    );
  }

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
    if (highlightChatLine == null || workspaceTab !== "transcript") return;
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
  }, [highlightChatLine, workspaceTab, messages, scrollElRef]);

  const handleStop = useCallback(() => {
    void cancelRoomRun().catch(() => {});
    for (const id of getRunningSessionIds()) {
      updateSessionRun(id, { running: false });
    }
    clearRunWatchdog();
    runWatchdogRef.current = window.setTimeout(() => {
      for (const id of getRunningSessionIds()) {
        updateSessionRun(id, { runBusy: false });
      }
      runWatchdogRef.current = null;
    }, 45_000);
  }, []);

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
          : recommended?.action_key ?? null,
    };
  }

  function notifyConsensusSync(proposal: ConsensusDryRunProposal) {
    const title = consensusDryRunNotifyTitle(proposal.excerpt);
    const body = consensusDryRunNotifyBody(
      proposal.summary,
      proposal.recommended?.what,
    );
    dispatchNotification(
      {
        tier: "P1",
        title,
        body,
        sessionId: sessionId ?? undefined,
        kind: proposal.recommended ? "dry_run" : "plan_sync",
        entityId: proposal.action_key ?? proposal.excerpt,
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
      efficiency: boolean = efficiencyOn,
    ) => {
      if (mode === "execute") return;
      const roomMode = mode === "plan" ? "plan" : "discuss";
      const {
        agents,
        agentRounds,
        reviewMode: useReviewMode,
        consensusMode: useConsensusMode,
        efficiencyMode: useEfficiencyMode,
      } = resolveTurnSend(profile, selected, efficiency);
      if (agents.length === 0) return;

      const sendText =
        msgText.trim() ||
        (filesToSend.length ? attachmentSendTopic(filesToSend) : "");
      if (!sendText) return;

      let runKey = resolveRunSessionKey(sessionId, activeSessionIdRef.current);
      const userMsg = topicAsUserMessage(sendText);
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
            activeSessionIdRef.current = String(ev.session_id);
            activeSessionId = activeSessionIdRef.current;
            if (runKey === PENDING_KEY || runKey !== activeSessionId) {
              migratePendingSessionRun(activeSessionId);
              runKey = activeSessionId;
            }
            if (!sessionId && onSessionMetaRefresh) {
              void onSessionMetaRefresh(activeSessionIdRef.current);
            }
          }
          if (t === "run_cancelled") {
            userStopped = true;
          }
          if (t === "agent_round_start" && Number(ev.round) > 1) {
            const round = Number(ev.round);
            updateSessionRun(runKey, { topologyActive: null });
            const rid = `round-divider-${round}`;
            const resolved = resolveTurnSend(profile, selected, efficiency);
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
          if (t === "consensus_plan_synced") {
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
          if (t === "consensus_plan_sync_failed") {
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
              (ev.questions as unknown[]).map((q) => String(q)).filter(Boolean),
            );
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
            updateSessionRun(runKey, { topologyActive: { agent: aid, round } });
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
          if (t === "agent_done" && ev.agent) {
            const aid = String(ev.agent);
            const round = Number(ev.round ?? 1);
            updateSessionRun(runKey, (snap) => {
              const n = new Set(snap.topologyDone);
              n.add(`${aid}:${round}`);
              return { topologyActive: null, topologyDone: n };
            });
            patchTurnMessages(runKey, (m) => [
              ...m.filter((x) => x.id !== `typing-${aid}-r${round}`),
              {
                id: `msg-${aid}-r${round}-${Date.now()}`,
                role: aid as LiveMsg["role"],
                label: agentLabel(aid),
                body: String(ev.content ?? "") || "(empty)",
                parallelRound: round,
                envelope: ev.envelope as LiveMsg["envelope"],
                envelopeParseError: ev.envelope_parse_error === true,
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
          if (t === "complete" && ev.session_id) {
            activeSessionId = String(ev.session_id);
            if (typeof ev.send_receipt === "string") {
              lastSendReceipt = ev.send_receipt;
            }
            if (ev.inbox_pending === true) {
              setInboxReloadKey((k) => k + 1);
              setInboxPendingChip(true);
              setInboxPopupDismissed(false);
              dispatchNotification(
                {
                  tier: "P1",
                  title: "Human decision pending",
                  body: "Transcript popup 또는 Inspector Inbox에서 처리하세요.",
                  sessionId: activeSessionId,
                  kind: "human_inbox",
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
              void cancelRoomRun().catch(() => {});
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
            efficiencyMode: useEfficiencyMode,
            turnProfile: profile,
            researchMode:
              researchMode || normalizeTurnProfile(profile) === "specialist",
            workspaceId: sessionId ? undefined : workspaceId,
            workspacePath:
              sessionId || workspaceId !== CUSTOM_WORKSPACE_ID
                ? undefined
                : workspacePath ?? undefined,
            agentCapabilities: capabilitiesForApi(agentCapabilities),
          },
        );
        if (runFailed) {
          throw new Error("run failed");
        }
        if (activeSessionId) {
          activeSessionIdRef.current = activeSessionId;
          await onSessionChange(activeSessionId);
          if (mode === "plan") {
            openPlanTab();
          }
        } else if (mode === "plan") {
          openPlanTab();
        }
        setPendingFiles([]);
        setSendReceipt(sendReceiptLabel(lastSendReceipt, mode, userStopped));
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
        if (activeSessionId ?? sessionId) {
          changePlanAfterSend(false);
        }
      }
    },
    [
      selected,
      sessionId,
      onSessionChange,
      onSessionMetaRefresh,
      composeMode,
      turnProfile,
      efficiencyOn,
      researchMode,
      workspaceId,
      workspacePath,
      agentCapabilities,
      refreshSessionMeta,
    ],
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
    if (running || runBusy || synthesizing || !sessionId || messages.length === 0) return;
    void executeSynthesizeOnly(roomPermissions(selected));
  }

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
      const parsed = rawText ? matchSlashCommand(rawText, slashCommands) : command;
      const args =
        rawText?.replace(/^\/[^\s]+\s*/, "").trim() ??
        command.slash.replace(/^\//, "");
      try {
        const res = await runSessionCommand(sessionId, {
          command_id: (parsed ?? command).id,
          args,
        });
        if (res.kind === "server") {
          refreshSessionMeta();
          setCommandHint("명령 실행 완료");
        } else if (res.text) {
          setCommandHint(res.text.slice(0, 240));
        } else if (res.detail) {
          setCommandHint(res.detail);
        } else {
          setCommandHint("명령 실행됨");
        }
        setText("");
      } catch (e) {
        setCommandHint(e instanceof Error ? e.message : "명령 실패");
      }
    },
    [sessionId, slashCommands, refreshSessionMeta, handleStop],
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
    void executeSend(msg, pendingFiles, roomPermissions(selected));
    setText("");
  }

  const focusPlanAction = (actionIndex: number) => {
    setPlanActionFocusIndex(actionIndex);
    openReviewTab();
  };
  const focusObjection = useCallback(
    (objectionId: string) => {
      setInspectorTab("tasks");
      setTaskBarFocusObjection({ id: objectionId, nonce: Date.now() });
    },
    [setInspectorTab],
  );
  const focusTask = useCallback(
    (taskId: string) => {
      openTranscriptTab();
      setInspectorTab("tasks");
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
    [roomTasks, session?.chat, messages, openTranscriptTab, setInspectorTab],
  );

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
  const composerObjectionNotice = planExecuteObjection
    ? {
        message: planExecute.openObjectionBlock?.message ?? "미해결 이의가 있습니다.",
        objectionId: planExecuteObjection.id,
        actionIndex: planExecuteObjection.plan_action_index,
      }
    : null;
  const composerPlaceholder = firstOpenBlock?.plan_action_index
    ? `plan #${firstOpenBlock.plan_action_index} BLOCK 해결 후 execute`
    : "메시지";

  const readyCount = agents.filter((a) => a.ready).length;
  const agentsBlocked =
    !running && !loading && selected.length === 0 && agents.length >= 0;
  const title = isNew ? "Session" : session?.topic || sessionId || "Session";
  const setupMeta = sessionSetupSummary(session?.meta, session?.run);
  const attachments = session?.attachments ?? [];
  const planMeta = buildPlanMetaView(session?.run);
  const currentPlanRevision =
    planMeta.lastUpdate?.completed_at || planMeta.lastUpdate?.ts || null;
  const planRefWarnings = analyzePlanRefWarnings(planMd, session?.chat);
  const turnResolved = resolveTurnSend(turnProfile, selected, efficiencyOn);
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
    running && workspaceTab === "transcript" && typingAgents.length === 0
      ? turnResolved.agents.map((id) => ({
          id: `pending-${id}`,
          role: id as LiveMsg["role"],
          label: agentLabel(id),
        }))
      : [];

  const paletteActions = useMemo(
    () => {
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
    },
    [
      setWorkspaceTab,
      running,
      handleStop,
      handleReleaseRunLock,
      onOpenSettings,
      slashCommands,
      openTranscriptTab,
      focusComposerInput,
    ],
  );

  const sessionArtifacts = roomTasks?.artifacts ?? [];

  return (
    <div
      className={`room-workspace-shell${
        !isNew && !inspectorOpen ? " room-workspace-shell--inspector-collapsed" : ""
      }`}
    >
      <CommandPalette actions={paletteActions} />
      <ChatPaneBody className="workspace-main">
      <ChatToolbar
        sidebarOpen={sidebarOpen}
        onToggleSidebar={onToggleSidebar}
        title={title}
        meta={
          isNew
            ? `${formatRoomModelLine(agents) || "Claude · Codex · Cursor"} (${readyCount}/3)`
            : setupMeta ?? undefined
        }
        trailing={
          <>
            <AgentPicker
              agents={agents}
              selected={selected}
              disabled={running}
              onToggle={toggleAgent}
              inline
            />
            {!isNew ? (
              <ContextSidebarToggle
                open={inspectorOpen}
                onToggle={toggleInspector}
                badgeCount={notificationUnread}
              />
            ) : null}
          </>
        }
      />

      {isNew && setupWorkspaces.length > 0 ? (
        <SessionSetupBar
          workspaces={setupWorkspaces}
          workspaceId={workspaceId}
          workspacePath={workspacePath}
          onWorkspaceChange={setWorkspaceId}
          onBrowseFolder={() => void browseWorkspaceFolder()}
          researchMode={researchMode}
          onResearchModeChange={(on) => {
            setResearchModeState(on);
            try {
              localStorage.setItem("agent-lab-research-mode", on ? "1" : "0");
            } catch {
              /* ignore */
            }
          }}
          disabled={running || runBusy}
        />
      ) : null}

      {isNew ? (
        <AgentSessionSettings
          capabilities={agentCapabilities}
          onChange={handleAgentCapabilitiesChange}
          resolvedCwd={resolvedAgentCwd}
          selectedAgents={selected}
          disabled={running || runBusy}
          compact={false}
          onSave={sessionId ? () => saveAgentCapabilities() : undefined}
          saveBusy={agentCapsBusy}
          saveHint={agentCapsHint ?? "첫 메시지 전송 시 세션에 함께 저장됩니다"}
        />
      ) : null}

      <WorkspaceTabBar
        active={workspaceTab}
        onChange={setWorkspaceTab}
        isNew={isNew}
        trailing={
          !isNew ? (
            <div
              className="view-tabs-bar__trailing"
              onBlur={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                  setViewOptionsOpen(false);
                }
              }}
            >
              <button
                type="button"
                className={`view-options-btn${viewOptionsOpen ? " is-active" : ""}`}
                aria-label="보기 옵션"
                title="보기 옵션"
                onClick={() => setViewOptionsOpen((v) => !v)}
              >
                ⋯
              </button>
              {viewOptionsOpen && workspaceTab === "transcript" ? (
                <div className="view-options-popover" role="menu">
                  <label className="view-options-row">
                    <input
                      type="checkbox"
                      checked={showHumanSynthesis}
                      onChange={(e) => {
                        const on = e.target.checked;
                        setShowHumanSynthesisState(on);
                        setShowHumanSynthesis(on);
                      }}
                    />
                    Human 요약
                    {hiddenAgentCount > 0 && showHumanSynthesis ? (
                      <span className="room-peer-toggle__count">
                        {" "}
                        (+{hiddenAgentCount})
                      </span>
                    ) : null}
                  </label>
                  <label
                    className="view-options-row"
                    title={
                      showHumanSynthesis
                        ? "Human 요약 모드에서는 동료 채널을 켤 수 없습니다"
                        : "에이전트 동료 발화(peer) 표시"
                    }
                  >
                    <input
                      type="checkbox"
                      checked={showPeerChannel}
                      onChange={(e) => setShowPeerChannel(e.target.checked)}
                      disabled={showHumanSynthesis}
                    />
                    동료 채널
                    {hiddenPeerCount > 0 && !showPeerChannel && !showHumanSynthesis ? (
                      <span className="room-peer-toggle__count">
                        {" "}
                        ({hiddenPeerCount})
                      </span>
                    ) : null}
                  </label>
                </div>
              ) : null}
            </div>
          ) : null
        }
      />

      {showExecuteQueueStrip && planExecute.activePending ? (
        <div className="workspace-event-strip workspace-event-strip--review">
          <ExecuteQueueBar
            pending={planExecute.activePending}
            storedActions={(session?.run?.actions as StoredPlanAction[]) ?? []}
            busy={executeBusy}
            disabled={running || synthesizing || runBusy}
            compact
            onApprove={() => void planExecute.approve()}
            onReject={() => void planExecute.reject()}
            onOpenPlan={openWorkTab}
          />
        </div>
      ) : null}

      {showConsensusDryRunGate && consensusProposal ? (
        <div className="workspace-event-strip workspace-event-strip--review">
          <ConsensusDryRunGateBar
            proposal={consensusProposal}
            busy={consensusGateBusy || executeBusy}
            disabled={running || synthesizing || runBusy}
            onDryRun={handleConsensusDryRun}
            onOpenPlan={openWorkTab}
            onDismiss={dismissConsensusProposal}
          />
        </div>
      ) : null}

      {workspaceTab === "work" && sessionId ? (
        <div
          className="messages-scroll messages-scroll--document workspace-panel--work"
          ref={workScrollRef}
        >
          <WorkPanel
          sessionId={sessionId}
          session={session}
          planMd={planMd}
          planMeta={planMeta}
          planRefWarnings={planRefWarnings}
          planAfterSend={planAfterSend}
          onPlanAfterSendChange={changePlanAfterSend}
          synthesizing={synthesizing}
          running={running}
          runBusy={runBusy}
          onSynthesizeNow={handleSynthesizeNow}
          hasPendingExecution={hasPendingExecution}
          consensusProposal={consensusProposal}
          consensusGateBusy={consensusGateBusy}
          executeBusy={executeBusy}
          onConsensusDryRun={() => void handleConsensusDryRun()}
          onDismissConsensus={dismissConsensusProposal}
          onApproveExecute={() => void planExecute.approve()}
          onRejectExecute={() => void planExecute.reject()}
          onPlanRefClick={handlePlanRefClick}
          onFocusTask={focusTask}
          onFocusObjection={focusObjection}
          onSessionUpdated={refreshSessionMeta}
          roomTasks={roomTasks}
          cursorReady={agents.some((a) => a.id === "cursor" && a.ready)}
          storedActions={(session?.run?.actions as StoredPlanAction[]) ?? []}
          activePending={planExecute.activePending}
        />
        </div>
      ) : null}

      {workspaceTab === "run" && !isNew ? (
        <div className="messages-scroll messages-scroll--document workspace-panel--run">
          <div className="workspace-document-panel workspace-document-panel--run-turn">
            <TurnRunPanel
              totalRounds={turnResolved.agentRounds}
              reviewMode={turnResolved.reviewMode}
              agents={turnResolved.agents}
              doneKeys={topologyDone}
              active={topologyActive}
              turnMessages={turnMessages}
              running={running}
              runBusy={runBusy}
              longRunning={longRunning}
              runLockStuck={runLockStuck}
              releasingLock={releasingLock}
              onStop={handleStop}
              onReleaseLock={() => void handleReleaseRunLock()}
            />
          </div>
        </div>
      ) : null}

      {workspaceTab === "artifacts" && !isNew ? (
        <div className="messages-scroll messages-scroll--document workspace-panel--artifacts">
          <div className="workspace-document-panel">
            <div className="workspace-document-panel__header">
              <strong>Artifacts</strong>
              <span>Outputs saved during this session</span>
            </div>
            {sessionArtifacts.length > 0 ? (
              <ul className="workspace-artifacts-list">
                {[...sessionArtifacts].reverse().map((art) => (
                  <li key={art.id ?? art.path ?? `${art.producer}-${art.kind}`}>
                    <strong>
                      {art.producer} · {art.kind}
                    </strong>
                    {art.summary ? <span>{art.summary}</span> : null}
                    {art.path ? (
                      <span className="workspace-artifacts-list__path">{art.path}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="workspace-empty-state">저장된 산출물이 없습니다.</p>
            )}
          </div>
        </div>
      ) : null}

      {workspaceTab === "transcript" || isNew ? (
        <>
          <div
            className="messages-scroll messages-scroll--document workspace-panel--transcript"
            ref={scrollRef}
          >
            <div className="workspace-document-panel workspace-transcript-panel">
            {loading && !isNew ? (
              <div className="empty-chat">Transcript 불러오는 중…</div>
            ) : visibleMessages.length === 0 && !running ? (
              <div className="empty-chat">메시지를 입력하세요</div>
            ) : null}
            {visibleMessages.map((m) => {
              if (m.roundDivider) {
                return (
                  <div
                    key={m.id}
                    className="chat-round-divider"
                    aria-label={m.body}
                  >
                    {m.body}
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
                  />
                );
              }
              const highlighted = highlightChatLine === m.chatLineIndex;
              return (
                <div
                  key={m.id}
                  className={[
                    "chat-line",
                    m.role === "you" || m.sent ? "chat-line--you" : undefined,
                    m.peerChannel ? "chat-line--peer" : undefined,
                    m.humanSynthesis ? "chat-line--synthesis" : undefined,
                    highlighted ? "chat-line--highlight" : undefined,
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  {...(m.chatLineIndex != null
                    ? { "data-chat-line": m.chatLineIndex }
                    : {})}
                >
                <ChatBubble
                  message={m}
                  typing={m.typing}
                  highlighted={highlighted}
                  presentation="console"
                />
                </div>
              );
            })}
            {pendingReplyAgents.map((a) => (
              <div key={a.id} className="chat-line">
                <ReplyWaitingBubble
                  agent={a.role}
                  label={a.label}
                  activities={[]}
                />
              </div>
            ))}
            </div>
          </div>
        </>
      ) : null}

      {clarifierQuestions && clarifierQuestions.length > 0 ? (
        <div
          className="clarifier-banner"
          role="region"
          aria-label="확인 질문"
        >
          <strong className="clarifier-banner__title">확인 질문</strong>
          <ul>
            {clarifierQuestions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
          <p className="clarifier-banner__hint">
            답을 메시지에 포함해 다시 내면 에이전트가 시작됩니다.
          </p>
        </div>
      ) : null}

      {combinedError ? (
        <div className="error-banner" role="alert" aria-label="룸 오류">
          {combinedError}
        </div>
      ) : null}

      {agentsBlocked && !combinedError ? (
        <div className="error-banner" role="status" aria-label="에이전트 준비 상태">
          {agents.length === 0
            ? "API(8765)에 연결할 수 없습니다. Tauri 앱을 완전히 종료한 뒤 make tauri-dev로 다시 시작하세요."
            : `준비된 에이전트가 없습니다 (${readyCount}/3). cursor/codex/claude 로그인을 확인하세요.`}
        </div>
      ) : null}

      {transcriptActive && (
        <ScrollToBottomButton
          visible={showJumpButton}
          onClick={scrollToBottom}
        />
      )}

      {sendReceipt && shouldShowSendReceiptOnChatTab(sendReceipt) ? (
        <div className="composer-send-receipt" role="status">
          {sendReceipt}
        </div>
      ) : null}

      {inboxPendingChip ? (
        <button
          type="button"
          className="composer-inbox-pending"
          onClick={openHumanInbox}
        >
          Human Inbox 대기
        </button>
      ) : null}

      <ComposerPreflightBar agents={healthAgents} selected={selected} />

      {transcriptActive && !inboxPopupDismissed ? (
        <HumanInboxPanel
          sessionId={sessionId}
          reloadKey={inboxReloadKey}
          planRevision={currentPlanRevision}
          onResolved={handleInboxResolved}
          onBuildStarted={handleInboxBuildStarted}
          onDismiss={() => {
            setInboxPopupDismissed(true);
            setInboxPendingChip(true);
          }}
          onOpenInbox={openHumanInbox}
          disabled={running || synthesizing || runBusy}
          presentation="popup"
        />
      ) : null}

      <ChatComposer
        className={[
          turnProfile === "review" ? "composer--review" : undefined,
          turnProfile === "free" ? "composer--free" : undefined,
          efficiencyOn ? "composer--efficient" : undefined,
          composerModeVariant === "consensus" ? "composer--consensus-mode" : undefined,
        ]
          .filter(Boolean)
          .join(" ") || undefined}
        value={text}
        onChange={setText}
        onSend={handleSend}
        slashCommands={slashCommands}
        onSlashExecute={(cmd) => void runSlashCommand(cmd, cmd.slash)}
        disabled={composerInputLocked}
        sendDisabled={composerSendLocked}
        placeholder={composerPlaceholder}
        showPlanToggle={false}
        showModeChipHint={false}
        running={running}
        onStop={handleStop}
        files={pendingFiles}
        onFilesAdd={addFiles}
        onFileRemove={(id) =>
          setPendingFiles((f) => f.filter((x) => x.id !== id))
        }
        sessionAttachments={attachments}
        turnProfile={turnProfile}
        onTurnProfileChange={changeTurnProfile}
        planAfterSend={!isNew ? planAfterSend : undefined}
        efficiencyOn={efficiencyOn}
        onEfficiencyChange={(on) => {
          setEfficiencyOnState(on);
          setEfficiencyMode(on);
        }}
        planStaleNotice={null}
        objectionNotice={composerObjectionNotice}
        onFocusObjection={focusObjection}
        turnCostHint={turnCost.compactLabel}
        fullTeamConfirm={null}
      />

      {commandHint ? (
        <p className="composer-command-hint" role="status">
          {commandHint}
        </p>
      ) : null}

      <AgentPermissionAlert
        open={permOpen}
        selectedAgents={selected}
        onCancel={() => {
          setPermOpen(false);
          if (pendingSend) {
            setText(pendingSend.text);
            setPendingFiles(pendingSend.files);
            setPendingSend(null);
          }
        }}
        onConfirm={(permissions) => {
          setPermOpen(false);
          if (pendingSend) {
            void executeSend(
              pendingSend.text,
              pendingSend.files,
              permissions,
              pendingSend.planAfterSend ? "plan" : "discuss",
              pendingSend.turnProfile,
              pendingSend.efficiencyOn,
            );
            setPendingSend(null);
          }
        }}
      />
      </ChatPaneBody>

      {!isNew ? (
        <InspectorPane
          active={inspectorTab}
          onChange={setInspectorTab}
          open={inspectorOpen}
          width={inspectorWidth}
          onWidthChange={setInspectorWidthState}
          onWidthCommit={commitInspectorWidth}
          badges={{
            activity: notificationUnread,
            tasks: inboxPendingChip ? 1 : undefined,
          }}
        >
          {inspectorTab === "activity" ? (
            <div className="inspector-pane__section inspector-pane__section-card">
              <NotificationCenter onOpen={openNotificationTarget} />
            </div>
          ) : null}
          {inspectorTab === "tasks" ? (
            <div className="inspector-pane__section inspector-pane__section-card">
              <section
                className={`goal-loop-banner goal-loop-banner--${goalView.loop.status ?? "unset"}`}
                aria-label="세션 목표"
              >
                <div className="goal-loop-banner__head">
                  <strong>세션 목표</strong>
                  {goalView.loop.status ? (
                    <span
                      className={`goal-oracle-badge goal-oracle-badge--${goalView.loop.status}`}
                    >
                      {goalView.loop.status === "achieved"
                        ? "목표 달성"
                        : goalView.loop.last_check?.verdict === "fail"
                          ? "Oracle FAIL"
                          : "진행 중"}
                    </span>
                  ) : null}
                </div>
                <div className="goal-loop-banner__controls">
                  <input
                    type="text"
                    value={goalText}
                    onChange={(e) => setGoalText(e.target.value)}
                    placeholder="Human이 판단할 세션 목표"
                    disabled={goalBusy}
                  />
                  <button
                    type="button"
                    className="room-task-bar__cta"
                    disabled={goalBusy || !goalText.trim()}
                    onClick={() => void saveSessionGoal()}
                  >
                    목표 설정
                  </button>
                  {goalView.goal.text ? (
                    <button
                      type="button"
                      className="room-task-bar__cta"
                      disabled={goalBusy || goalView.loop.status === "achieved"}
                      onClick={() => void runGoalCheck()}
                    >
                      Oracle 재검
                    </button>
                  ) : null}
                </div>
                {goalView.loop.last_check?.detail ? (
                  <p className="goal-loop-banner__detail">
                    {goalView.loop.last_check.detail}
                  </p>
                ) : null}
                {goalView.loop.last_check?.verdict === "fail" ? (
                  <button
                    type="button"
                    className="room-task-bar__cta room-task-bar__cta--primary"
                    onClick={() =>
                      requestComposerPrefill(
                        goalView.loop.continue_prompt ??
                          `세션 목표를 달성하기 위해 한 턴 더 토론해 주세요: ${goalView.loop.last_check?.detail ?? ""}`,
                      )
                    }
                  >
                    한 턴 더 토론
                  </button>
                ) : null}
                {goalError ? (
                  <p className="goal-loop-banner__error">{goalError}</p>
                ) : null}
              </section>
              <RoomTaskBar
                sessionId={sessionId ?? ""}
                payload={roomTasks}
                context={taskBarContext}
                loading={tasksLoading}
                executions={planExecutions}
                focusObjection={taskBarFocusObjection}
                onRefresh={refreshTasks}
                onFocusPlanAction={focusPlanAction}
                onFocusTask={focusTask}
                onRequestComposerPrefill={requestComposerPrefill}
              />
              <HumanInboxPanel
                sessionId={sessionId}
                reloadKey={inboxReloadKey}
                planRevision={currentPlanRevision}
                onResolved={handleInboxResolved}
                onBuildStarted={handleInboxBuildStarted}
                disabled={running || synthesizing || runBusy}
                presentation="inspector"
              />
            </div>
          ) : null}
          {inspectorTab === "quick" ? (
            <div className="inspector-pane__section inspector-pane__section-card">
              <QuickSettingsPanel
                capabilities={agentCapabilities}
                resolvedCwd={resolvedAgentCwd}
                selectedAgents={selected}
                onOpenFullSettings={onOpenSettings}
              />
            </div>
          ) : null}
        </InspectorPane>
      ) : null}
    </div>
  );
}
