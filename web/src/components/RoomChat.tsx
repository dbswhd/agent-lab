import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AgentOption, PlanActionItem, SessionDetail } from "../api/client";
import {
  cancelRoomRun,
  checkSessionGoal,
  releaseRoomRunLock,
  runRoom,
  setSessionGoal,
  type AgentHealthRow,
  type GoalLoopRecord,
  type SessionGoalRecord,
} from "../api/client";
import {
  agentLabel,
  chatLineToMessage,
  parseTranscript,
  topicAsUserMessage,
  type ChatMessage,
} from "../utils/transcript";
import { AgentPicker } from "./AgentPicker";
import { ContextSidebarToggle } from "./ContextSidebarToggle";
import {
  ChatBubble,
  isReplyWaitRole,
  ReplyWaitingBubble,
} from "./ChatBubble";
import { ChatComposer, type PendingFile } from "./ChatComposer";
import { ChatPaneBody } from "./ChatPaneBody";
import { ChatToolbar } from "./ChatToolbar";
import { ContextPreviewPanel } from "./ContextPreviewPanel";
import { PlanDocument } from "./PlanDocument";
import { PlanExecutePanel } from "./PlanExecutePanel";
import {
  ScrollToBottomButton,
  useMessagesScroll,
  useScrollToTop,
} from "./ScrollToBottomButton";
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
import { notifyDesktop } from "../utils/desktopNotify";
import { buildPlanMetaView } from "../utils/planMeta";
import {
  CONTENT_TAB_SHORTCUT_EVENT,
  type ContentTab,
} from "../utils/desktopShortcuts";
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
import { TurnProgressStrip } from "./TurnProgressStrip";
import { CollapsibleGlassPanel } from "./CollapsibleGlassPanel";
import {
  getContextSidebarOpen,
  setContextSidebarOpen,
} from "../utils/contextSidebarPrefs";
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
import { PlanTabToolbar } from "./PlanTabToolbar";
import { ComposerPreflightBar } from "./ComposerPreflightBar";
import { RoomRunStatusBar } from "./RoomRunStatusBar";

const LONG_RUN_HINT_MS = Number(
  import.meta.env.VITE_ROOM_LONG_RUN_HINT_MS || "180000",
);

type LiveMsg = ChatMessage & { typing?: boolean };

type PartialTurnNotice = {
  failedAgents: string[];
  succeededAgents: string[];
};

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
}: Props) {
  const { push: pushMacNotification } = useMacNotifications();
  const [selected, setSelected] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const [messages, setMessages] = useState<LiveMsg[]>([]);
  const [running, setRunning] = useState(false);
  const [runBusy, setRunBusy] = useState(false);
  const [synthesizing, setSynthesizing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"chat" | "plan">("chat");
  const [planActionFocusIndex, setPlanActionFocusIndex] = useState<
    number | null
  >(null);
  const [showPeerChannel, setShowPeerChannel] = useState(false);
  const [showHumanSynthesis, setShowHumanSynthesis] = useState(true);
  const [viewOptionsOpen, setViewOptionsOpen] = useState(false);
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
  const [fullTeamConfirmed, setFullTeamConfirmed] = useState(false);
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
  const [topologyDone, setTopologyDone] = useState<Set<string>>(
    () => new Set(),
  );
  const [topologyActive, setTopologyActive] = useState<{
    agent: string;
    round: number;
  } | null>(null);
  const [contextOpen, setContextOpenState] = useState(getContextSidebarOpen);
  const [sendReceipt, setSendReceipt] = useState<string | null>(null);
  const sendReceiptTimerRef = useRef<number | null>(null);
  const [clarifierQuestions, setClarifierQuestions] = useState<string[] | null>(
    null,
  );
  const [goalText, setGoalText] = useState("");
  const [goalBusy, setGoalBusy] = useState(false);
  const [goalError, setGoalError] = useState<string | null>(null);
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
  const [partialTurnNotice, setPartialTurnNotice] =
    useState<PartialTurnNotice | null>(null);

  function parseAgentList(value: unknown): string[] {
    return Array.isArray(value)
      ? value.map((x) => String(x)).filter(Boolean)
      : [];
  }

  function showPartialTurnNotice(failedAgents: string[], succeededAgents: string[]) {
    if (failedAgents.length === 0) return;
    setPartialTurnNotice({ failedAgents, succeededAgents });
  }

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
    const raw = session?.run?.agent_capabilities;
    if (raw && typeof raw === "object") {
      setAgentCapabilities(parseAgentCapabilities(raw));
    }
  }, [sessionId, session?.run?.agent_capabilities]);

  const goalView = useMemo(() => goalLoopView(session?.run), [session?.run]);
  useEffect(() => {
    setGoalText(goalView.goal.text ?? "");
    setGoalError(null);
  }, [sessionId, goalView.goal.text]);

  useEffect(() => {
    if (!sessionId) {
      setResolvedAgentCwd({});
      return;
    }
    const perms = roomPermissions(selected);
    void fetchSessionAgentCapabilities(sessionId, perms as Record<string, unknown>)
      .then((r) => {
        if (r.agent_capabilities) {
          setAgentCapabilities(parseAgentCapabilities(r.agent_capabilities));
        }
        setResolvedAgentCwd(r.resolved_cwd ?? {});
      })
      .catch(() => {});
  }, [sessionId, selected]);

  function changeTurnProfile(profile: ComposerTurnProfile) {
    setTurnProfileState(profile);
    setTurnStrategy(profile);
    setTurnProfile(profile);
  }

  function changePlanAfterSend(on: boolean) {
    setPlanAfterSendState(on);
    setPlanAfterSend(on);
  }

  const refreshTasks = useCallback(() => {
    if (!sessionId) {
      setRoomTasks(null);
      return;
    }
    setTasksLoading(true);
    void fetchSessionTasks(sessionId)
      .then(setRoomTasks)
      .catch(() => setRoomTasks(null))
      .finally(() => setTasksLoading(false));
  }, [sessionId]);

  function refreshSessionMeta() {
    if (!sessionId) return;
    if (onSessionMetaRefresh) {
      void onSessionMetaRefresh(sessionId);
    } else {
      void onSessionChange(sessionId);
    }
    refreshTasks();
  }

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
      refreshSessionMeta();
    } catch (e) {
      setAgentCapsHint(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setAgentCapsBusy(false);
    }
  }, [sessionId, agentCapabilities]);

  useEffect(() => {
    refreshTasks();
  }, [refreshTasks, session?.run, session?.chat?.length]);

  const planExecute = usePlanExecute({
    sessionId,
    run: session?.run,
    onUpdated: refreshSessionMeta,
  });

  const showExecuteQueue =
    Boolean(sessionId) &&
    tab === "chat" &&
    Boolean(planExecute.activePending);
  const showConsensusDryRunGate =
    Boolean(sessionId) &&
    tab === "chat" &&
    !showExecuteQueue &&
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
  const chatActive = tab === "chat" || (tab === "plan" && !planMd);
  const typingAgents = messages.filter(
    (m) => m.typing && isReplyWaitRole(m.role),
  );
  const pendingReplyCount =
    running && tab === "chat" && typingAgents.length === 0
      ? resolveTurnSend(turnProfile, selected, efficiencyOn).agents.length
      : 0;
  const { scrollRef, scrollElRef, showJumpButton, scrollToBottom } = useMessagesScroll(
    [messages, running, pendingReplyCount, selected.join(",")],
    chatActive,
    `${sessionId ?? "new"}:chat`,
  );
  const { scrollRef: planScrollRef, scrollElRef: planScrollElRef } =
    useScrollToTop(tab === "plan" && Boolean(planMd), `${sessionId ?? "new"}:plan`);

  const planExecutions = useMemo(
    () =>
      (session?.run?.executions as PlanExecutionRecord[] | undefined) ?? [],
    [session?.run?.executions],
  );

  useEffect(() => {
    if (tab !== "plan" || planActionFocusIndex == null) return;
    const index = planActionFocusIndex;
    const timer = window.setTimeout(() => {
      const el = planScrollElRef.current?.querySelector(
        `[data-plan-action-index="${index}"]`,
      );
      el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      setPlanActionFocusIndex(null);
    }, 80);
    return () => window.clearTimeout(timer);
  }, [tab, planActionFocusIndex, planScrollElRef]);

  const isNew = !sessionId;
  const waitingForSession = Boolean(sessionId && !session && loading);
  const composerInputLocked = waitingForSession;
  const preflightBlocked = selected.some((id) => {
    const row = healthAgents.find((a) => a.id === id);
    return Boolean(row && !row.ready);
  });
  const composerSendLocked =
    runBusy ||
    running ||
    synthesizing ||
    (loading && waitingForSession) ||
    selected.length === 0 ||
    preflightBlocked ||
    (turnCost.requiresConfirm && !fullTeamConfirmed) ||
    (!text.trim() && pendingFiles.length === 0);
  const sessionReviewMode = Boolean(
    (session?.run?.last_turn as { review_mode?: boolean } | undefined)
      ?.review_mode,
  );

  useEffect(() => {
    const ready = agents.filter((a) => a.ready).map((a) => a.id);
    setSelected(ready);
  }, [agents]);

  const prevSessionIdRef = useRef<string | null>(sessionId);

  useEffect(() => {
    const prev = prevSessionIdRef.current;
    prevSessionIdRef.current = sessionId;

    clearRunWatchdog();
    setTopologyDone(new Set());
    setTopologyActive(null);
    setPartialTurnNotice(null);

    if (prev === sessionId) return;

    if (sessionId === null) {
      setRunBusy(false);
      setRunning(false);
      setSynthesizing(false);
      return;
    }

    if (prev !== null && prev !== sessionId) {
      setRunBusy(false);
      setRunning(false);
      setSynthesizing(false);
    }
  }, [sessionId]);

  function toggleContextSidebar() {
    const next = !contextOpen;
    setContextOpenState(next);
    setContextSidebarOpen(next);
  }

  useEffect(() => {
    if (sessionId !== null) return;
    setRunning(false);
    setRunBusy(false);
    setSynthesizing(false);
    setText("");
    setError(null);
    setPendingFiles([]);
    setTab("chat");
  }, [sessionId]);

  useEffect(() => {
    setFullTeamConfirmed(false);
  }, [turnProfile, selected, efficiencyOn, sessionId]);

  useEffect(() => {
    syncedChatRef.current = "";
  }, [sessionId]);

  useEffect(() => {
    setConsensusProposal(null);
    setPartialTurnNotice(null);
  }, [sessionId]);

  useEffect(() => {
    const lastTurn = session?.run?.last_turn as
      | {
          status?: string;
          failed_agents?: unknown;
          succeeded_agents?: unknown;
        }
      | undefined;
    if (lastTurn?.status === "partial") {
      showPartialTurnNotice(
        parseAgentList(lastTurn.failed_agents),
        parseAgentList(lastTurn.succeeded_agents),
      );
    } else if (!running && !runBusy) {
      setPartialTurnNotice(null);
    }
  }, [session?.run?.last_turn, running, runBusy]);

  useEffect(() => {
    if (running || runBusy) return;

    if (session) {
      const fp = chatFingerprint(session);
      if (fp !== syncedChatRef.current) {
        syncedChatRef.current = fp;
        setMessages(sessionToMessages(session, sessionReviewMode));
      }
      setPlanMd(session.plan_md || "");
    }
  }, [session, running, runBusy, sessionReviewMode]);

  useEffect(() => {
    if (sessionId !== null || running || runBusy) return;
    syncedChatRef.current = "";
    setMessages([]);
    setPlanMd("");
  }, [sessionId, running, runBusy]);

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

  const handlePlanRefClick = useCallback((lineNumber: number) => {
    setTab("chat");
    setHighlightChatLine(lineNumber - 1);
  }, []);

  useEffect(() => {
    if (highlightChatLine == null || tab !== "chat") return;
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
  }, [highlightChatLine, tab, messages, scrollElRef]);

  const handleStop = useCallback(() => {
    void cancelRoomRun().catch(() => {});
    setRunning(false);
    clearRunWatchdog();
    runWatchdogRef.current = window.setTimeout(() => {
      setRunBusy(false);
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
    pushMacNotification({ title, body });
    notifyDesktop(title, body);
  }

  function notifyConsensusFailure(excerpt?: string, message?: string) {
    const title = agreementPlanSyncFailedLabel(excerpt, message);
    pushMacNotification({ title });
    notifyDesktop(title);
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

      setTopologyDone(new Set());
      setTopologyActive(null);
      setRunBusy(true);
      setRunning(true);
      clearRunWatchdog();
      scheduleLongRunHint();
      setRunLockStuck(false);
      setError(null);
      setPartialTurnNotice(null);
      setClarifierQuestions(null);
      const userMsg = topicAsUserMessage(sendText);
      setMessages((m) => [...m, userMsg]);
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
            activeSessionId = String(ev.session_id);
          }
          if (t === "run_cancelled") {
            userStopped = true;
          }
          if (t === "agent_round_start" && Number(ev.round) > 1) {
            const round = Number(ev.round);
            setTopologyActive(null);
            const rid = `round-divider-${round}`;
            const resolved = resolveTurnSend(profile, selected, efficiency);
            setMessages((m) => [
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
            setMessages((m) => [
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
            setMessages((m) => [
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
            setMessages((m) => [
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
            setTopologyActive({ agent: aid, round });
            setMessages((m) => [
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
            setMessages((m) =>
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
            setTopologyActive(null);
            setTopologyDone((prev) => {
              const n = new Set(prev);
              n.add(`${aid}:${round}`);
              return n;
            });
            setMessages((m) => [
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
            setMessages((m) => [
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
            setMessages((m) => [
              ...m,
              {
                id: `turn-failed-${Date.now()}`,
                role: "system",
                label: "시스템",
                body: `[턴 실패${aid ? ` · ${agentLabel(aid)}` : ""}] ${reason}${detail}`,
              },
            ]);
          }
          if (t === "turn_partial") {
            const failedAgents = parseAgentList(ev.failed_agents);
            const succeededAgents = parseAgentList(ev.succeeded_agents);
            showPartialTurnNotice(failedAgents, succeededAgents);
          }
          if (t === "complete" && ev.session_id) {
            activeSessionId = String(ev.session_id);
            if (typeof ev.send_receipt === "string") {
              lastSendReceipt = ev.send_receipt;
            }
            if (ev.status === "partial") {
              showPartialTurnNotice(
                parseAgentList(ev.failed_agents),
                parseAgentList(ev.succeeded_agents),
              );
            }
          }
          if (t === "run_failed") {
            runFailed = true;
            const msg = String(ev.message ?? "run failed");
            setError(msg);
            setRunLockStuck(true);
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
          await onSessionChange(activeSessionId);
          if (mode === "plan") {
            setTab("plan");
          }
        } else if (mode === "plan") {
          setTab("plan");
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
        setMessages((m) => m.filter((x) => !x.typing));
        setRunBusy(false);
        setRunning(false);
        if (sessionId) {
          changePlanAfterSend(false);
        }
      }
    },
    [
      selected,
      sessionId,
      onSessionChange,
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
      setSynthesizing(true);
      setRunBusy(true);
      setRunning(true);
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
        setTab("plan");
        await onSessionChange(sessionId);
      } catch (e) {
        setError(String(e));
      } finally {
        clearRunWatchdog();
        setSynthesizing(false);
        setRunBusy(false);
        setRunning(false);
      }
    },
    [selected, sessionId, synthesizing, onSessionChange],
  );

  function handleSynthesizeNow() {
    if (running || runBusy || synthesizing || !sessionId || messages.length === 0) return;
    void executeSynthesizeOnly(roomPermissions(selected));
  }

  function handleSend() {
    const msg = text.trim();
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
    if (turnCost.requiresConfirm && !fullTeamConfirmed) return;
    void executeSend(msg, pendingFiles, roomPermissions(selected));
    setText("");
    setFullTeamConfirmed(false);
  }

  const openPlanTab = () => setTab("plan");
  const focusPlanAction = (actionIndex: number) => {
    setPlanActionFocusIndex(actionIndex);
    setTab("plan");
  };
  const focusObjection = useCallback((objectionId: string) => {
    setTab("chat");
    setTaskBarFocusObjection({ id: objectionId, nonce: Date.now() });
  }, []);
  const focusTask = useCallback(
    (taskId: string) => {
      setTab("chat");
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
    [roomTasks, session?.chat, messages],
  );

  const requestComposerPrefill = useCallback((prefill: string) => {
    setTab("chat");
    setText(prefill);
    focusComposerInput();
  }, []);
  const executeBusy = planExecute.busy;
  const combinedError = error || planExecute.error;
  const pendingExecuteCount = planExecute.activePending ? 1 : 0;
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
  const title = isNew ? "3자 룸" : session?.topic || sessionId || "대화";
  const setupMeta = sessionSetupSummary(session?.meta, session?.run);
  const attachments = session?.attachments ?? [];
  const planMeta = buildPlanMetaView(session?.run);
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
  const showProgressStrip = !isNew && tab === "chat" && running;
  const pendingReplyAgents =
    running && tab === "chat" && typingAgents.length === 0
      ? turnResolved.agents.map((id) => ({
          id: `pending-${id}`,
          role: id as LiveMsg["role"],
          label: agentLabel(id),
        }))
      : [];

  useEffect(() => {
    function onContentTabShortcut(event: Event) {
      if (isNew) return;
      const nextTab = (event as CustomEvent<ContentTab>).detail;
      if (nextTab === "chat" || nextTab === "plan") setTab(nextTab);
    }

    window.addEventListener(CONTENT_TAB_SHORTCUT_EVENT, onContentTabShortcut);
    return () =>
      window.removeEventListener(CONTENT_TAB_SHORTCUT_EVENT, onContentTabShortcut);
  }, [isNew]);

  return (
    <div
      className={`room-chat-split${contextOpen && !isNew ? " room-chat-split--context-open" : ""}`}
    >
      <ChatPaneBody>
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
                open={contextOpen}
                onToggle={toggleContextSidebar}
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

      <AgentSessionSettings
        capabilities={agentCapabilities}
        onChange={setAgentCapabilities}
        resolvedCwd={resolvedAgentCwd}
        selectedAgents={selected}
        disabled={running || runBusy}
        compact={!isNew}
        onSave={sessionId ? () => saveAgentCapabilities() : undefined}
        saveBusy={agentCapsBusy}
        saveHint={
          sessionId
            ? agentCapsHint
            : "첫 메시지 전송 시 세션에 함께 저장됩니다"
        }
      />

      <div className="view-tabs-bar">
        {!isNew ? (
          <div
            className="mac-segmented view-tabs-seg view-tabs-bar__leading"
            role="tablist"
          >
            <button
              type="button"
              role="tab"
              aria-selected={tab === "chat"}
              className={tab === "chat" ? "active" : ""}
              onClick={() => setTab("chat")}
              title="대화 (⌘1)"
            >
              대화
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === "plan"}
              className={tab === "plan" ? "active" : ""}
              onClick={() => setTab("plan")}
              title="plan (⌘2)"
            >
              plan
              {pendingExecuteCount > 0 ? (
                <span className="view-tabs-bar__pending" aria-hidden>
                  {" "}
                  · 승인
                </span>
              ) : null}
            </button>
          </div>
        ) : (
          <div className="view-tabs-bar__leading">
            <span className="view-tabs-bar__static" aria-hidden>
              대화
            </span>
          </div>
        )}
        {!isNew && tab === "chat" ? (
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
            {viewOptionsOpen ? (
              <div className="view-options-popover" role="menu">
                <label className="view-options-row">
                  <input
                    type="checkbox"
                    checked={showHumanSynthesis}
                    onChange={(e) => setShowHumanSynthesis(e.target.checked)}
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
        ) : null}
      </div>

      {!isNew && tab === "chat" ? (
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
          {goalError ? <p className="goal-loop-banner__error">{goalError}</p> : null}
        </section>
      ) : null}

      {!isNew && tab === "chat" ? (
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
      ) : null}

      {showProgressStrip ? (
        <div className="run-progress-slot" aria-live="polite">
          <TurnProgressStrip
            totalRounds={turnResolved.agentRounds}
            reviewMode={turnResolved.reviewMode}
            agents={turnResolved.agents}
            doneKeys={topologyDone}
            active={topologyActive}
          />
        </div>
      ) : null}

      {tab === "plan" && planMd ? (
        <div
          className="messages-scroll messages-scroll--document"
          ref={planScrollRef}
        >
          <div className="plan-tab-cluster">
          <PlanTabToolbar
            planAfterSend={planAfterSend}
            onPlanAfterSendChange={changePlanAfterSend}
            synthesizing={synthesizing}
            running={running}
            disabled={runBusy}
            onSynthesizeNow={handleSynthesizeNow}
            planMeta={planMeta}
          />
          {planMeta.pendingAgreement || planMeta.reviewTurnLabel ? (
            <CollapsibleGlassPanel
              className="plan-detail-panel"
              title="plan 알림"
              summary={
                planMeta.pendingAgreement
                  ? "합의 반영 재시도 필요"
                  : planMeta.reviewTurnLabel ?? "plan 상세"
              }
              variant={planMeta.pendingAgreement ? "warn" : "default"}
              defaultOpen={Boolean(planMeta.pendingAgreement)}
            >
              {planMeta.pendingAgreement ? (
                <div className="plan-meta-bar plan-meta-bar--sync_failed">
                  <p className="plan-meta-bar__line">{planMeta.freshnessLabel}</p>
                  <button
                    type="button"
                    className="room-plan-btn room-plan-btn--accent"
                    disabled={running || synthesizing}
                    onClick={handleSynthesizeNow}
                  >
                    {synthesizing ? "정리 중…" : "다시 정리"}
                  </button>
                </div>
              ) : null}
              {planMeta.reviewTurnLabel ? (
                <span className="plan-meta-bar__review-badge">
                  {planMeta.reviewTurnLabel}
                </span>
              ) : null}
              {planMeta.chatLineLabel ? (
                <p className="plan-detail-panel__lines">
                  출처 {planMeta.chatLineLabel} · {planMeta.agentsLabel}
                </p>
              ) : null}
            </CollapsibleGlassPanel>
          ) : null}
          {planRefWarnings.bannerText ? (
            <CollapsibleGlassPanel
              className="plan-ref-warn-panel"
              title="ref 경고"
              summary={planRefWarnings.bannerText}
              variant="warn"
              defaultOpen={false}
            >
              <p className="plan-ref-warn-panel__text">
                {planRefWarnings.bannerText}
              </p>
            </CollapsibleGlassPanel>
          ) : null}
          <PlanExecutePanel
            sessionId={sessionId!}
            run={session?.run}
            linkedTasks={roomTasks?.tasks}
            cursorReady={agents.some((a) => a.id === "cursor" && a.ready)}
            disabled={running || synthesizing || runBusy}
            onChatRefClick={handlePlanRefClick}
            onFocusTask={focusTask}
            onFocusObjection={focusObjection}
            onUpdated={() => {
              if (!sessionId) return;
              if (onSessionMetaRefresh) {
                void onSessionMetaRefresh(sessionId);
              } else {
                void onSessionChange(sessionId);
              }
            }}
          />
          <PlanDocument
            planMd={planMd}
            skipExecuteSections
            onRefClick={handlePlanRefClick}
          />
          </div>
        </div>
      ) : (
        <>
          {showExecuteQueue && planExecute.activePending ? (
            <ExecuteQueueBar
              pending={planExecute.activePending}
              storedActions={
                (session?.run?.actions as StoredPlanAction[]) ?? []
              }
              busy={executeBusy}
              disabled={running || synthesizing || runBusy}
              onApprove={() => void planExecute.approve()}
              onReject={() => void planExecute.reject()}
              onOpenPlan={openPlanTab}
            />
          ) : null}
          {showConsensusDryRunGate && consensusProposal ? (
            <ConsensusDryRunGateBar
              proposal={consensusProposal}
              busy={consensusGateBusy || executeBusy}
              disabled={running || synthesizing || runBusy}
              onDryRun={handleConsensusDryRun}
              onOpenPlan={openPlanTab}
              onDismiss={dismissConsensusProposal}
            />
          ) : null}
          {partialTurnNotice ? (
            <div
              className="room-partial-banner"
              role="status"
              aria-label="일부 에이전트 실패"
            >
              <strong>일부 에이전트 실패</strong>
              <span>나머지 응답은 저장됨</span>
              <span className="room-partial-banner__agents">
                실패: {partialTurnNotice.failedAgents.map(agentLabel).join(", ")}
              </span>
            </div>
          ) : null}
        <div className="messages-scroll" ref={scrollRef}>
          {loading && !isNew ? (
            <div className="empty-chat">대화 불러오는 중…</div>
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
                />
              </div>
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
        </>
      )}

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

      {chatActive && (
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

      <RoomRunStatusBar
        longRunning={longRunning && running}
        runLockStuck={runLockStuck && !running}
        onCancel={handleStop}
        onReleaseLock={() => void handleReleaseRunLock()}
        releasing={releasingLock}
      />

      <ComposerPreflightBar agents={healthAgents} selected={selected} />

      <ChatComposer
        className={[
          turnProfile === "review" ? "composer--review" : undefined,
          turnProfile === "free" ? "composer--free" : undefined,
          efficiencyOn ? "composer--efficiency" : undefined,
          composerModeVariant === "consensus" ? "composer--consensus-mode" : undefined,
        ]
          .filter(Boolean)
          .join(" ") || undefined}
        value={text}
        onChange={setText}
        onSend={handleSend}
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
        turnCostHint={turnCost.label}
        fullTeamConfirm={
          turnCost.requiresConfirm
            ? {
                required: true,
                checked: fullTeamConfirmed,
                label: `${turnCost.estimatedAgentCalls}회 호출 이해함`,
                detail: "풀 팀 실행은 이번 턴에만 확인합니다.",
                disabled: composerInputLocked || running || runBusy || synthesizing,
                onChange: setFullTeamConfirmed,
              }
            : null
        }
      />

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

      {!isNew && contextOpen ? (
        <aside className="context-sidebar" aria-label="에이전트 컨텍스트">
          <ContextPreviewPanel
            sessionId={sessionId}
            session={session}
            selectedAgents={selected}
            turnProfile={turnProfile}
            efficiencyOn={efficiencyOn}
            disabled={running}
            onClose={toggleContextSidebar}
          />
        </aside>
      ) : null}
    </div>
  );
}
