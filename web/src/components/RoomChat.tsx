import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentOption, SessionDetail } from "../api/client";
import { fetchSession, runRoom } from "../api/client";
import {
  agentLabel,
  chatLineToMessage,
  parseTranscript,
  topicAsUserMessage,
  type ChatMessage,
} from "../utils/transcript";
import { AgentPicker } from "./AgentPicker";
import { Avatar } from "./Avatar";
import { ChatBubble } from "./ChatBubble";
import { ChatComposer, type PendingFile } from "./ChatComposer";
import { ChatPaneBody } from "./ChatPaneBody";
import { AgentPermissionAlert } from "./AgentPermissionAlert";
import type { AgentPermissions } from "../utils/agentPermissions";
import {
  hasSavedPermissionDefaults,
  loadDefaultPermissions,
} from "../utils/agentPermissions";

type LiveMsg = ChatMessage & { typing?: boolean };

type Props = {
  agents: AgentOption[];
  sessionId: string | null;
  session: SessionDetail | null;
  loading?: boolean;
  onSessionChange: (sessionId: string) => void;
};

function sessionToMessages(session: SessionDetail): LiveMsg[] {
  if (session.chat && session.chat.length > 0) {
    return session.chat.map((line, i) => chatLineToMessage(line, i));
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
}: Props) {
  const [selected, setSelected] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const [messages, setMessages] = useState<LiveMsg[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"chat" | "plan">("chat");
  const [planMd, setPlanMd] = useState("");
  const [permOpen, setPermOpen] = useState(false);
  const [pendingSend, setPendingSend] = useState<{
    text: string;
    files: PendingFile[];
  } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, running]);

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
    async (msgText: string, filesToSend: PendingFile[], permissions: AgentPermissions) => {
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
          if (t === "agent_start" && ev.agent) {
            const aid = String(ev.agent);
            setMessages((m) => [
              ...m.filter((x) => x.id !== `typing-${aid}`),
              {
                id: `typing-${aid}`,
                role: aid as LiveMsg["role"],
                label: agentLabel(aid),
                body: "",
                typing: true,
              },
            ]);
          }
          if (t === "agent_done" && ev.agent) {
            const aid = String(ev.agent);
            setMessages((m) => [
              ...m.filter((x) => x.id !== `typing-${aid}`),
              {
                id: `msg-${aid}-${Date.now()}`,
                role: aid as LiveMsg["role"],
                label: agentLabel(aid),
                body: String(ev.content ?? "") || "(empty)",
              },
            ]);
          }
          if (t === "agent_error" && ev.agent) {
            const aid = String(ev.agent);
            setMessages((m) => [
              ...m.filter((x) => x.id !== `typing-${aid}`),
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
            synthesize: true,
            permissions,
          },
        );
        if (activeSessionId) {
          const detail = await fetchSession(activeSessionId);
          setMessages(sessionToMessages(detail));
          setPlanMd(detail.plan_md || "");
          onSessionChange(activeSessionId);
        }
      } catch (e) {
        setError(String(e));
      } finally {
        setMessages((m) => m.filter((x) => !x.typing));
        setRunning(false);
      }
    },
    [selected, sessionId, onSessionChange],
  );

  function handleSend() {
    if (!text.trim() || running || selected.length === 0) return;
    const needsPerm =
      (selected.includes("cursor") || selected.includes("codex")) &&
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

  if (loading && !isNew) {
    return (
      <ChatPaneBody>
        <div className="empty-chat">불러오는 중…</div>
      </ChatPaneBody>
    );
  }

  return (
    <ChatPaneBody>
      <header className="chat-header">
        <Avatar role="you" />
        <div className="chat-header-text">
          <h2>{title}</h2>
          <div className="chat-header-meta">
            {isNew
              ? `Cursor · Codex · Claude (${readyCount}/3 준비됨)`
              : String(
                  session?.run?.workflow_id ??
                    session?.meta?.workflow ??
                    "room.parallel",
                )}
          </div>
        </div>
      </header>

      <AgentPicker
        agents={agents}
        selected={selected}
        disabled={running}
        onToggle={toggleAgent}
      />

      {!isNew && (
        <div className="view-tabs mac-segmented" role="tablist">
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
        </div>
      )}

      {tab === "plan" && planMd ? (
        <div className="messages-scroll">
          <pre className="pinned-plan-body plan-pre">{planMd}</pre>
        </div>
      ) : (
        <div className="messages-scroll" ref={scrollRef}>
          {messages.length === 0 && !running && (
            <div className="empty-chat">
              메시지를 내면 선택한 에이전트가 함께 답합니다.
              <span className="empty-chat-hint">
                파일 첨부 가능 · plan.md는 대화 후 자동 갱신
              </span>
            </div>
          )}
          {messages.map((m) => (
            <ChatBubble key={m.id} message={m} typing={m.typing} />
          ))}
        </div>
      )}

      {error && <div className="error-banner">{error}</div>}

      <ChatComposer
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
