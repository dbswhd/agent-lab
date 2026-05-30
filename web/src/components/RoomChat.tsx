import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentOption, RoomMode, SessionDetail } from "../api/client";
import { cancelRoomRun, fetchSession, runRoom } from "../api/client";
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
import { RoomRunControls } from "./RoomRunControls";
import {
  ScrollToBottomButton,
  useMessagesScroll,
} from "./ScrollToBottomButton";
import { AgentPermissionAlert } from "./AgentPermissionAlert";
import type { AgentPermissions } from "../utils/agentPermissions";
import {
  hasSavedPermissionDefaults,
  loadDefaultPermissions,
} from "../utils/agentPermissions";
import { buildPlanMetaView } from "../utils/planMeta";
import { analyzePlanRefWarnings } from "../utils/planRefWarnings";
import {
  consensusEndLabel,
  consensusIncompleteLabel,
  roundDividerLabel,
} from "../utils/roundTopology";
import {
  getEfficiencyMode,
  setEfficiencyMode,
} from "../utils/efficiencyPrefs";
import {
  getTurnProfile,
  resolveTurnSend,
  setTurnProfile,
  type ComposerTurnProfile,
} from "../utils/turnProfile";
import { formatRoomModelLine } from "../utils/roomModels";
import { TurnProgressStrip } from "./TurnProgressStrip";
import { CollapsibleGlassPanel } from "./CollapsibleGlassPanel";
import {
  getContextSidebarOpen,
  setContextSidebarOpen,
} from "../utils/contextSidebarPrefs";

type LiveMsg = ChatMessage & { typing?: boolean };

type Props = {
  agents: AgentOption[];
  sessionId: string | null;
  session: SessionDetail | null;
  loading?: boolean;
  onSessionChange: (sessionId: string) => void | Promise<void>;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
};

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
  sessionId,
  session,
  loading,
  onSessionChange,
  sidebarOpen,
  onToggleSidebar,
}: Props) {
  const [selected, setSelected] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const [messages, setMessages] = useState<LiveMsg[]>([]);
  const [running, setRunning] = useState(false);
  const [runBusy, setRunBusy] = useState(false);
  const [synthesizing, setSynthesizing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"chat" | "plan">("chat");
  const [planMd, setPlanMd] = useState("");
  const [permOpen, setPermOpen] = useState(false);
  const [composeMode, setComposeMode] = useState<RoomMode>("discuss");
  const [turnProfile, setTurnProfileState] = useState(getTurnProfile);
  const [efficiencyOn, setEfficiencyOnState] = useState(getEfficiencyMode);
  const [pendingSend, setPendingSend] = useState<{
    text: string;
    files: PendingFile[];
    turnProfile: ComposerTurnProfile;
    composeMode: RoomMode;
    efficiencyOn: boolean;
  } | null>(null);
  const [highlightChatLine, setHighlightChatLine] = useState<number | null>(
    null,
  );
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
  const runWatchdogRef = useRef<number | null>(null);

  function clearRunWatchdog() {
    if (runWatchdogRef.current != null) {
      window.clearTimeout(runWatchdogRef.current);
      runWatchdogRef.current = null;
    }
  }
  const chatActive = tab !== "plan" || !planMd;
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
    sessionId,
  );

  const isNew = !sessionId;
  const waitingForSession = Boolean(sessionId && !session && loading);
  const composerInputLocked = waitingForSession;
  const composerSendLocked =
    runBusy ||
    running ||
    synthesizing ||
    (loading && waitingForSession) ||
    selected.length === 0;
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
    if (running || runBusy || loading) return;

    if (session) {
      setMessages(sessionToMessages(session, sessionReviewMode));
      setPlanMd(session.plan_md || "");
      return;
    }

    if (!sessionId) {
      setMessages([]);
      setPlanMd("");
    }
  }, [session, sessionId, running, runBusy, sessionReviewMode, loading]);

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

  const executeSend = useCallback(
    async (
      msgText: string,
      filesToSend: PendingFile[],
      permissions: AgentPermissions,
      mode: RoomMode = composeMode,
      profile: ComposerTurnProfile = turnProfile,
      efficiency: boolean = efficiencyOn,
    ) => {
      const {
        agents,
        agentRounds,
        reviewMode: useReviewMode,
        consensusMode: useConsensusMode,
        efficiencyMode: useEfficiencyMode,
      } = resolveTurnSend(profile, selected, efficiency);
      if (agents.length === 0) return;

      setTopologyDone(new Set());
      setTopologyActive(null);
      setRunBusy(true);
      setRunning(true);
      clearRunWatchdog();
      runWatchdogRef.current = window.setTimeout(() => {
        setRunBusy(false);
        setRunning(false);
        runWatchdogRef.current = null;
      }, 120_000);
      setError(null);
      const userMsg = topicAsUserMessage(msgText);
      setMessages((m) => [...m, userMsg]);
      let userStopped = false;
      let activeSessionId = sessionId;

      try {
        let runFailed = false;
        await runRoom(
          msgText,
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
                  resolved.reviewMode,
                  resolved.consensusMode,
                ),
                roundDivider: round,
              },
            ]);
          }
          if (t === "consensus_reached") {
            const anchor = String(
              (ev.anchor as { agent?: string } | undefined)?.agent ?? "",
            );
            setMessages((m) => [
              ...m,
              {
                id: `consensus-end-${Date.now()}`,
                role: "system",
                label: "",
                body: consensusEndLabel(anchor, agentLabel),
              },
            ]);
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
              },
            ]);
          }
          if (t === "agent_error" && ev.agent) {
            const aid = String(ev.agent);
            const round = Number(ev.round ?? 1);
            setMessages((m) => [
              ...m.filter((x) => x.id !== `typing-${aid}-r${round}`),
              {
                id: `err-${aid}`,
                role: "system",
                label: "시스템",
                body: `[${agentLabel(aid)}] ${ev.message}`,
              },
            ]);
          }
          if (t === "complete" && ev.session_id) {
            activeSessionId = String(ev.session_id);
          }
          if (t === "error") {
            runFailed = true;
            const msg = String(ev.message ?? "run failed");
            setError(
              msg.includes("already in progress")
                ? "이전 실행이 아직 끝나지 않았습니다. 잠시 후 다시 시도하거나 답변 중지를 눌러 주세요."
                : msg,
            );
            if (msg.includes("already in progress")) {
              void cancelRoomRun().catch(() => {});
            }
          }
          },
          {
            sessionId: sessionId ?? undefined,
            files: filesToSend.map((p) => p.file),
            mode,
            agentRounds,
            permissions,
            reviewMode: useReviewMode,
            consensusMode: useConsensusMode,
            efficiencyMode: useEfficiencyMode,
          },
        );
        if (runFailed) {
          throw new Error("run failed");
        }
        if (activeSessionId) {
          void onSessionChange(activeSessionId);
          if (mode === "plan") {
            setTab("plan");
          }
        } else if (mode === "plan") {
          setTab("plan");
        }
        setSendReceipt(
          userStopped
            ? "답변 중지됨 · 부분 저장"
            : mode === "plan"
              ? "정리 완료 · plan 갱신"
              : "토론 저장 · plan 미변경",
        );
        if (sendReceiptTimerRef.current != null) {
          window.clearTimeout(sendReceiptTimerRef.current);
        }
        sendReceiptTimerRef.current = window.setTimeout(() => {
          setSendReceipt(null);
          sendReceiptTimerRef.current = null;
        }, 5000);
      } catch (e) {
        setError(String(e));
      } finally {
        clearRunWatchdog();
        setMessages((m) => m.filter((x) => !x.typing));
        setRunBusy(false);
        setRunning(false);
        if (sessionId) {
          setComposeMode("discuss");
          setTurnProfileState("discuss");
          setTurnProfile("discuss");
        }
      }
    },
    [selected, sessionId, onSessionChange, composeMode, turnProfile, efficiencyOn],
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
        const detail = await fetchSession(sessionId);
        const reviewHint = Boolean(
          (detail.run?.last_turn as { review_mode?: boolean } | undefined)
            ?.review_mode,
        );
        setMessages(sessionToMessages(detail, reviewHint));
        setPlanMd(detail.plan_md || "");
        setTab("plan");
        onSessionChange(sessionId);
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
    void executeSynthesizeOnly(loadDefaultPermissions());
  }

  function handleSend() {
    if (
      !text.trim() ||
      runBusy ||
      running ||
      synthesizing ||
      (loading && waitingForSession) ||
      selected.length === 0
    ) {
      return;
    }
    const needsPerm =
      (selected.includes("cursor") ||
        selected.includes("codex") ||
        selected.includes("claude")) &&
      !hasSavedPermissionDefaults();
    if (needsPerm) {
      setPendingSend({
        text: text.trim(),
        files: [...pendingFiles],
        turnProfile,
        composeMode,
        efficiencyOn,
      });
      setText("");
      setPendingFiles([]);
      setPermOpen(true);
      return;
    }
    void executeSend(text.trim(), pendingFiles, loadDefaultPermissions());
    setText("");
    setPendingFiles([]);
  }

  const readyCount = agents.filter((a) => a.ready).length;
  const agentsBlocked =
    !running && !loading && selected.length === 0 && agents.length >= 0;
  const title = isNew ? "3자 룸" : session?.topic || sessionId || "대화";
  const attachments = session?.attachments ?? [];
  const planMeta = buildPlanMetaView(session?.run);
  const planRefWarnings = analyzePlanRefWarnings(planMd, session?.chat);
  const turnResolved = resolveTurnSend(turnProfile, selected, efficiencyOn);
  const showProgressStrip = !isNew && tab === "chat" && running;
  const pendingReplyAgents =
    running && tab === "chat" && typingAgents.length === 0
      ? turnResolved.agents.map((id) => ({
          id: `pending-${id}`,
          role: id as LiveMsg["role"],
          label: agentLabel(id),
        }))
      : [];

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
            : undefined
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

      <div className="view-tabs-bar">
        <div className="view-tabs-bar__leading" role="tablist">
          {!isNew ? (
            <>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "chat"}
                className={tab === "chat" ? "active" : ""}
                onClick={() => setTab("chat")}
              >
                대화
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "plan"}
                className={tab === "plan" ? "active" : ""}
                onClick={() => setTab("plan")}
              >
                plan.md
              </button>
            </>
          ) : (
            <span className="view-tabs-bar__static" aria-hidden>
              대화
            </span>
          )}
        </div>
        <RoomRunControls
          composeMode={composeMode}
          onComposeModeChange={setComposeMode}
          running={running}
          synthesizing={synthesizing}
          showSynthesizeNow={!isNew && messages.length > 0}
          onSynthesizeNow={handleSynthesizeNow}
        />
      </div>

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
        <div className="messages-scroll messages-scroll--document">
          <div
            className={`plan-meta-bar plan-meta-bar--${planMeta.freshness}`}
            role="status"
          >
            <div className="plan-meta-bar__row">
              <span className="plan-meta-bar__line">
                마지막 정리: {planMeta.timeLabel} · {planMeta.triggerLabel}
                {planMeta.chatLineLabel
                  ? ` · ${planMeta.chatLineLabel}`
                  : ""}
                {planMeta.freshness === "stale" &&
                planMeta.messagesSincePlan != null
                  ? ` · 채팅 +${planMeta.messagesSincePlan}줄`
                  : ""}
              </span>
              {planMeta.freshness === "stale" ? (
                <button
                  type="button"
                  className="room-plan-btn room-plan-btn--accent"
                  disabled={running || synthesizing}
                  onClick={handleSynthesizeNow}
                >
                  {synthesizing ? "정리 중…" : "지금 정리"}
                </button>
              ) : (
                <span className="plan-meta-bar__freshness">최신</span>
              )}
            </div>
            {planMeta.reviewTurnLabel ? (
              <span className="plan-meta-bar__review-badge">
                {planMeta.reviewTurnLabel}
              </span>
            ) : null}
          </div>
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
          <PlanDocument planMd={planMd} onRefClick={handlePlanRefClick} />
        </div>
      ) : (
        <div className="messages-scroll" ref={scrollRef}>
          {loading && !isNew ? (
            <div className="empty-chat">대화 불러오는 중…</div>
          ) : messages.length === 0 && !running ? (
            <div className="empty-chat">메시지를 입력하세요</div>
          ) : null}
          {messages.map((m) => {
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
      )}

      {error && <div className="error-banner">{error}</div>}

      {agentsBlocked && !error ? (
        <div className="error-banner" role="status">
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

      {sendReceipt ? (
        <div className="composer-send-receipt" role="status">
          {sendReceipt}
        </div>
      ) : null}

      <ChatComposer
        className={[
          turnProfile === "review" ? "composer--review" : undefined,
          turnProfile === "free" ? "composer--free" : undefined,
          efficiencyOn ? "composer--efficiency" : undefined,
        ]
          .filter(Boolean)
          .join(" ") || undefined}
        value={text}
        onChange={setText}
        onSend={handleSend}
        disabled={composerInputLocked}
        sendDisabled={composerSendLocked}
        running={running}
        onStop={handleStop}
        files={pendingFiles}
        onFilesAdd={addFiles}
        onFileRemove={(id) =>
          setPendingFiles((f) => f.filter((x) => x.id !== id))
        }
        sessionAttachments={attachments}
        turnProfile={turnProfile}
        onTurnProfileChange={(p) => {
          setTurnProfileState(p);
          setTurnProfile(p);
        }}
        efficiencyOn={efficiencyOn}
        onEfficiencyChange={(on) => {
          setEfficiencyOnState(on);
          setEfficiencyMode(on);
        }}
        planStaleNotice={
          !isNew && tab === "chat" && planMeta.freshness === "stale"
            ? `plan.md가 채팅보다 뒤처짐${
                planMeta.messagesSincePlan != null
                  ? ` (+${planMeta.messagesSincePlan}줄)`
                  : ""
              } · 토론 후 「지금 정리」로 갱신`
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
              pendingSend.composeMode,
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
