import { useEffect, useRef, useState } from "react";
import type { AgentOption } from "../api/client";
import { runRoom } from "../api/client";
import { agentLabel, topicAsUserMessage, type ChatMessage } from "../utils/transcript";
import { ChatBubble } from "./ChatBubble";
import { Avatar } from "./Avatar";
import { ChatPaneBody } from "./ChatPaneBody";

type Props = {
  agents: AgentOption[];
  onComplete: (sessionId: string) => void;
};

type LiveMsg = ChatMessage & { typing?: boolean };

export function RoomPanel({ agents, onComplete }: Props) {
  const [topic, setTopic] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [messages, setMessages] = useState<LiveMsg[]>([]);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ready = agents.filter((a) => a.ready).map((a) => a.id);
    setSelected(ready);
  }, [agents]);

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

  async function handleSend() {
    if (!topic.trim() || running || selected.length === 0) return;
    setRunning(true);
    setError(null);
    const userMsg = topicAsUserMessage(topic.trim());
    setMessages([userMsg]);

    try {
      await runRoom(topic.trim(), selected, (ev) => {
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
          const content = String(ev.content ?? "");
          setMessages((m) => [
            ...m.filter((x) => x.id !== `typing-${aid}`),
            {
              id: `msg-${aid}-${Date.now()}`,
              role: aid as LiveMsg["role"],
              label: agentLabel(aid),
              body: content || "(empty)",
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
          onComplete(String(ev.session_id));
        }
        if (t === "error") {
          setError(String(ev.message ?? "room run failed"));
        }
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setMessages((m) => m.filter((x) => !x.typing));
      setRunning(false);
    }
  }

  const readyCount = agents.filter((a) => a.ready).length;

  return (
    <ChatPaneBody>
      <header className="chat-header">
        <Avatar role="you" />
        <div>
          <h2>3자 룸</h2>
          <div className="chat-header-meta">
            Cursor · Codex · Claude ({readyCount}/3 준비됨)
          </div>
        </div>
      </header>

      <div className="agent-chips" role="group" aria-label="참여 에이전트">
        <span className="agent-chips-label">참여</span>
        {agents.map((a) => {
          const on = selected.includes(a.id);
          const iconId = ["cursor", "codex", "claude"].includes(a.id)
            ? a.id
            : null;
          return (
            <button
              key={a.id}
              type="button"
              className={`agent-chip agent-chip--${a.id} ${on ? "on" : ""} ${!a.ready ? "off" : ""}`}
              disabled={!a.ready || running}
              onClick={() => toggleAgent(a.id)}
              aria-pressed={on}
            >
              {iconId && (
                <img
                  className="agent-chip-icon"
                  src={`/icons/${iconId}.png`}
                  alt=""
                  width={18}
                  height={18}
                />
              )}
              <span className="agent-chip-name">{a.label}</span>
              {a.ready ? (
                <span className="agent-chip-state">{on ? "포함" : "제외"}</span>
              ) : (
                <span className="agent-chip-state">미설정</span>
              )}
            </button>
          );
        })}
      </div>

      <div className="messages-scroll" ref={scrollRef}>
        {messages.length === 0 && !running && (
          <div className="empty-chat">
            참여할 에이전트를 고르고 주제를 보내세요.
            <br />
            <span className="empty-chat-hint">
              통제 워크플로: 병렬 1라운드 → plan.md 합성
            </span>
          </div>
        )}
        {messages.map((m) => (
          <ChatBubble key={m.id} message={m} typing={m.typing} />
        ))}
      </div>

      {error && <div className="error-banner">{error}</div>}

      <footer className="composer">
        <div className="composer-field">
          <textarea
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="메시지"
            disabled={running}
            rows={1}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
        </div>
        <button
          type="button"
          className="btn-send"
          disabled={running || !topic.trim() || selected.length === 0}
          onClick={handleSend}
          aria-label="전송"
        >
          ↑
        </button>
      </footer>
    </ChatPaneBody>
  );
}
