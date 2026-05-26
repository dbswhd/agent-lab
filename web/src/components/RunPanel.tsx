import { useEffect, useRef, useState } from "react";
import type { BackendOption } from "../api/client";
import { runGraph } from "../api/client";
import { topicAsUserMessage, type ChatMessage } from "../utils/transcript";
import { ChatBubble } from "./ChatBubble";
import { Avatar } from "./Avatar";
import { ChatPaneBody } from "./ChatPaneBody";

type Props = {
  backends: BackendOption[];
  defaultBackend: string;
  onComplete: (sessionId: string) => void;
};

const AGENT_ORDER = ["planner", "critic", "scribe"] as const;
const AGENT_META: Record<
  (typeof AGENT_ORDER)[number],
  { role: ChatMessage["role"]; label: string }
> = {
  planner: { role: "planner", label: "Planner" },
  critic: { role: "critic", label: "Critic" },
  scribe: { role: "scribe", label: "Scribe" },
};

type StepState = Record<string, string>;

export function RunPanel({ backends, defaultBackend, onComplete }: Props) {
  const [topic, setTopic] = useState("");
  const [backend, setBackend] = useState(defaultBackend);
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<StepState>({});
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setBackend(defaultBackend);
  }, [defaultBackend]);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [steps, running, topic]);

  async function handleRun() {
    if (!topic.trim() || running) return;
    setRunning(true);
    setSteps({});
    setError(null);
    try {
      await runGraph(topic.trim(), backend || null, (ev) => {
        if (ev.type === "step") {
          const node = String(ev.node);
          const status = String(ev.status);
          setSteps((s) => {
            const next = { ...s, [node]: status };
            const extra = ev.extra as Record<string, unknown> | undefined;
            if (extra?.chars != null) {
              next[`${node}_chars`] = String(extra.chars);
            }
            return next;
          });
        }
        if (ev.type === "complete" && ev.session_id) {
          onComplete(String(ev.session_id));
        }
        if (ev.type === "error") {
          setError(String(ev.message ?? "run failed"));
        }
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  }

  function renderAgentBubbles() {
    return AGENT_ORDER.map((node, index) => {
      const status = steps[node];
      const meta = AGENT_META[node];
      const prevDone = AGENT_ORDER.slice(0, index).every(
        (n) => steps[n] === "done",
      );
      const isTyping =
        status === "running" ||
        (running && prevDone && status !== "done" && !status);

      if (status === "done") {
        const chars = steps[`${node}_chars`];
        return (
          <ChatBubble
            key={node}
            message={{
              id: node,
              role: meta.role,
              label: meta.label,
              body: chars
                ? `(${chars}자) — 대화 탭에서 전문을 볼 수 있어요.`
                : "완료",
              sent: false,
            }}
          />
        );
      }
      if (isTyping) {
        return (
          <ChatBubble
            key={node}
            message={{
              id: `${node}-typing`,
              role: meta.role,
              label: meta.label,
              body: "",
              sent: false,
            }}
            typing
          />
        );
      }
      return null;
    });
  }

  const showThread = running || Object.keys(steps).length > 0;

  return (
    <ChatPaneBody>
      <header className="chat-header">
        <Avatar role="you" />
        <div>
          <h2>새 대화</h2>
          <div className="chat-header-meta">Planner → Critic → Scribe</div>
        </div>
      </header>

      <div className="messages-scroll" ref={scrollRef}>
        {!showThread && !topic.trim() && (
          <div className="empty-chat">
            주제를 입력하고 보내세요.
            <br />
            <span style={{ fontSize: "0.85rem", opacity: 0.8 }}>
              iMessage · Instagram DM · Telegram 스타일
            </span>
          </div>
        )}
        {topic.trim() && (
          <ChatBubble message={topicAsUserMessage(topic.trim())} />
        )}
        {showThread && renderAgentBubbles()}
        {steps.save === "done" && (
          <ChatBubble
            message={{
              id: "save",
              role: "system",
              label: "",
              body: "세션 저장됨",
            }}
          />
        )}
      </div>

      {error && <div className="error-banner">{error}</div>}

      <footer className="composer">
        <div className="composer-field">
          <textarea
            id="topic"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="메시지"
            disabled={running}
            rows={1}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleRun();
              }
            }}
          />
          <div className="composer-toolbar">
            <select
              value={backend}
              onChange={(e) => setBackend(e.target.value)}
              disabled={running || backends.length === 0}
              aria-label="백엔드"
            >
              {(backends.length
                ? backends
                : [{ id: "codex", label: "Codex", ready: false }]
              ).map((b) => (
                <option key={b.id} value={b.id}>
                  {b.label}
                </option>
              ))}
            </select>
            <span style={{ color: "var(--color-text-muted)" }}>
              ⏎ 전송 · ⇧⏎ 줄바꿈
            </span>
          </div>
        </div>
        <button
          type="button"
          className="btn-send"
          disabled={running || !topic.trim()}
          onClick={handleRun}
          aria-label="전송"
        >
          ↑
        </button>
      </footer>
    </ChatPaneBody>
  );
}
