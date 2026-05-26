import { useCallback, useEffect, useState } from "react";
import type { AgentOption, RoomMode, SessionDetail } from "../api/client";
import { fetchSession, runRoom } from "../api/client";
import {
  agentLabel,
  chatLineToMessage,
  parseTranscript,
  topicAsUserMessage,
  type ChatMessage,
} from "../utils/transcript";
import { AgentPicker } from "./AgentPicker";
import {
  ChatBubble,
  isReplyWaitRole,
  ReplyWaitingBubble,
} from "./ChatBubble";
import { ChatComposer, type PendingFile } from "./ChatComposer";
import { ChatPaneBody } from "./ChatPaneBody";
import { ChatToolbar } from "./ChatToolbar";
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
import { getAgentRounds, setAgentRounds } from "../utils/roomPrefs";
import { buildPlanMetaView } from "../utils/planMeta";
import { analyzePlanRefWarnings } from "../utils/planRefWarnings";

type LiveMsg = ChatMessage & { typing?: boolean };

type Props = {
  agents: AgentOption[];
  sessionId: string | null;
  session: SessionDetail | null;
  loading?: boolean;
  onSessionChange: (sessionId: string) => void;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
};

function sessionToMessages(session: SessionDetail): LiveMsg[] {
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
          body: "__round_divider__",
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
  const [synthesizing, setSynthesizing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"chat" | "plan">("chat");
  const [planMd, setPlanMd] = useState("");
  const [permOpen, setPermOpen] = useState(false);
  const [composeMode, setComposeMode] = useState<RoomMode>("discuss");
  const [reviewMode, setReviewMode] = useState(false);
  const [agentRounds, setAgentRoundsState] = useState(getAgentRounds);
  const [pendingSend, setPendingSend] = useState<{
    text: string;
    files: PendingFile[];
  } | null>(null);
  const chatActive = tab !== "plan" || !planMd;
  const typingAgents = messages.filter(
    (m) => m.typing && isReplyWaitRole(m.role),
  );
  const pendingReplyCount =
    running && tab === "chat" && typingAgents.length === 0
      ? selected.length
      : 0;
  const { scrollRef, showJumpButton, scrollToBottom } = useMessagesScroll(
    [messages, running, pendingReplyCount, selected.join(",")],
    chatActive,
    sessionId,
  );

  const isNew = !sessionId;

  useEffect(() => {
    const ready = agents.filter((a) => a.ready).map((a) => a.id);
    setSelected(ready);
  }, [agents]);

  useEffect(() => {
    if (session && !running) {
      setMessages(sessionToMessages(session));
      setPlanMd(session.plan_md || "");
    } else if (isNew && !running) {
      setMessages([]);
      setPlanMd("");
    }
  }, [session, isNew, running]);

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

  const executeSend = useCallback(
    async (
      msgText: string,
      filesToSend: PendingFile[],
      permissions: AgentPermissions,
      mode: RoomMode = composeMode,
      useReviewMode: boolean = reviewMode,
    ) => {
      setRunning(true);
      setError(null);
      const userMsg = topicAsUserMessage(msgText);
      setMessages((m) => [...m, userMsg]);

      try {
        let activeSessionId = sessionId;
        await runRoom(
          msgText,
          selected,
          (ev) => {
          const t = String(ev.type);
          if (t === "agent_round_start" && Number(ev.round) > 1) {
            const rid = `round-divider-${ev.round}`;
            setMessages((m) => [
              ...m.filter((x) => x.id !== rid),
              {
                id: rid,
                role: "system",
                label: "",
                body: "__round_divider__",
              },
            ]);
          }
          if (t === "agent_start" && ev.agent) {
            const aid = String(ev.agent);
            const round = Number(ev.round ?? 1);
            setMessages((m) => [
              ...m.filter((x) => x.id !== `typing-${aid}-r${round}`),
              {
                id: `typing-${aid}-r${round}`,
                role: aid as LiveMsg["role"],
                label: agentLabel(aid),
                body: "",
                typing: true,
                parallelRound: round,
              },
            ]);
          }
          if (t === "agent_done" && ev.agent) {
            const aid = String(ev.agent);
            const round = Number(ev.round ?? 1);
            setMessages((m) => [
              ...m.filter((x) => x.id !== `typing-${aid}-r${round}`),
              {
                id: `msg-${aid}-r${round}-${Date.now()}`,
                role: aid as LiveMsg["role"],
                label: agentLabel(aid),
                body: String(ev.content ?? "") || "(empty)",
                parallelRound: round,
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
            setError(String(ev.message ?? "run failed"));
          }
          },
          {
            sessionId: sessionId ?? undefined,
            files: filesToSend.map((p) => p.file),
            mode,
            agentRounds,
            permissions,
            reviewMode: useReviewMode,
          },
        );
        if (activeSessionId) {
          const detail = await fetchSession(activeSessionId);
          setMessages(sessionToMessages(detail));
          setPlanMd(detail.plan_md || "");
          onSessionChange(activeSessionId);
        }
        if (mode === "plan") {
          setTab("plan");
        }
      } catch (e) {
        setError(String(e));
      } finally {
        setMessages((m) => m.filter((x) => !x.typing));
        setRunning(false);
        setComposeMode("discuss");
        setReviewMode(false);
      }
    },
    [selected, sessionId, onSessionChange, composeMode, agentRounds, reviewMode],
  );

  const executeSynthesizeOnly = useCallback(
    async (permissions: AgentPermissions) => {
      if (!sessionId || synthesizing) return;
      const requestId = crypto.randomUUID();
      setSynthesizing(true);
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
            agentRounds,
            synthesizeOnly: true,
            requestId,
            permissions,
          },
        );
        const detail = await fetchSession(sessionId);
        setMessages(sessionToMessages(detail));
        setPlanMd(detail.plan_md || "");
        setTab("plan");
        onSessionChange(sessionId);
      } catch (e) {
        setError(String(e));
      } finally {
        setSynthesizing(false);
        setRunning(false);
      }
    },
    [selected, sessionId, agentRounds, synthesizing, onSessionChange],
  );

  function handleSynthesizeNow() {
    if (running || synthesizing || !sessionId || messages.length === 0) return;
    void executeSynthesizeOnly(loadDefaultPermissions());
  }

  function handleSend() {
    if (!text.trim() || running || selected.length === 0) return;
    const needsPerm =
      (selected.includes("cursor") ||
        selected.includes("codex") ||
        selected.includes("claude")) &&
      !hasSavedPermissionDefaults();
    if (needsPerm) {
      setPendingSend({ text: text.trim(), files: [...pendingFiles] });
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
  const title = isNew ? "3자 룸" : session?.topic || sessionId || "대화";
  const attachments = session?.attachments ?? [];
  const planMeta = buildPlanMetaView(session?.run);
  const planRefWarnings = analyzePlanRefWarnings(planMd, session?.chat);
  const pendingReplyAgents =
    running && tab === "chat" && typingAgents.length === 0
      ? selected.map((id) => ({
          id: `pending-${id}`,
          role: id as LiveMsg["role"],
          label: agentLabel(id),
        }))
      : [];

  if (loading && !isNew) {
    return (
      <ChatPaneBody>
        <div className="empty-chat">불러오는 중…</div>
      </ChatPaneBody>
    );
  }

  return (
    <ChatPaneBody>
      <ChatToolbar
        sidebarOpen={sidebarOpen}
        onToggleSidebar={onToggleSidebar}
        title={title}
        meta={
          isNew
            ? `Cursor · Codex · Claude (${readyCount}/3 준비됨)`
            : String(
                session?.run?.workflow_id ??
                  session?.meta?.workflow ??
                  "room.parallel",
              )
        }
        trailing={
          <AgentPicker
            agents={agents}
            selected={selected}
            disabled={running}
            onToggle={toggleAgent}
            inline
          />
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
          agentRounds={agentRounds}
          onAgentRoundsChange={(n) => {
            setAgentRounds(n);
            setAgentRoundsState(n);
          }}
          running={running}
          synthesizing={synthesizing}
          showSynthesizeNow={!isNew && messages.length > 0}
          onSynthesizeNow={handleSynthesizeNow}
          reviewMode={reviewMode}
          onReviewModeChange={setReviewMode}
        />
      </div>

      {tab === "plan" && planMd ? (
        <div className="messages-scroll messages-scroll--document">
          <div
            className={`plan-meta-bar plan-meta-bar--${planMeta.freshness}`}
            role="status"
          >
            <span className="plan-meta-bar__line">
              마지막 정리: {planMeta.timeLabel} · {planMeta.triggerLabel} ·
              agents: {planMeta.agentsLabel}
            </span>
            <span className="plan-meta-bar__freshness">
              {planMeta.freshnessLabel}
            </span>
          </div>
          {planMeta.reviewTurnLabel ? (
            <span className="plan-meta-bar__review">{planMeta.reviewTurnLabel}</span>
          ) : null}
          {planRefWarnings.bannerText ? (
            <div className="plan-ref-warn" role="note">
              {planRefWarnings.bannerText}
            </div>
          ) : null}
          <pre className="plan-pre">{planMd}</pre>
        </div>
      ) : (
        <div className="messages-scroll" ref={scrollRef}>
          {messages.length === 0 && !running && (
            <div className="empty-chat">
              메시지를 내면 선택한 에이전트가 함께 답하고, 이어서 서로의 말에
              한 번 더 반응합니다.
              <span className="empty-chat-hint">
                기본은 토론만 · plan.md는 「지금 정리」로 생성
              </span>
            </div>
          )}
          {messages.map((m) => {
            if (m.body === "__round_divider__") {
              return (
                <div key={m.id} className="chat-round-divider" aria-hidden>
                  토론
                </div>
              );
            }
            if (m.typing && isReplyWaitRole(m.role)) {
              return (
                <ReplyWaitingBubble
                  key={m.id}
                  agent={m.role}
                  label={m.label}
                />
              );
            }
            return <ChatBubble key={m.id} message={m} typing={m.typing} />;
          })}
          {pendingReplyAgents.map((a) => (
            <ReplyWaitingBubble
              key={a.id}
              agent={a.role}
              label={a.label}
            />
          ))}
        </div>
      )}

      {error && <div className="error-banner">{error}</div>}

      {chatActive && (
        <ScrollToBottomButton
          visible={showJumpButton}
          onClick={scrollToBottom}
        />
      )}

      <ChatComposer
        className={reviewMode ? "composer--review" : undefined}
        value={text}
        onChange={setText}
        onSend={handleSend}
        disabled={running || selected.length === 0}
        files={pendingFiles}
        onFilesAdd={addFiles}
        onFileRemove={(id) =>
          setPendingFiles((f) => f.filter((x) => x.id !== id))
        }
        sessionAttachments={attachments}
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
            );
            setPendingSend(null);
          }
        }}
      />
    </ChatPaneBody>
  );
}
