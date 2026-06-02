import { useEffect, useMemo, useState } from "react";
import type { BackendOption } from "../api/client";
import { runGraph } from "../api/client";
import { topicAsUserMessage, type ChatMessage } from "../utils/transcript";
import { ChatBubble } from "./ChatBubble";
import { ChatComposer } from "./ChatComposer";
import { ChatPaneBody } from "./ChatPaneBody";
import { ChatToolbar } from "./ChatToolbar";
import {
  ScrollToBottomButton,
  useMessagesScroll,
} from "./ScrollToBottomButton";

type Props = {
  backends: BackendOption[];
  defaultBackend: string;
  onComplete: (sessionId: string) => void;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
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

export function RunPanel({
  backends,
  defaultBackend,
  onComplete,
  sidebarOpen,
  onToggleSidebar,
}: Props) {
  const [topic, setTopic] = useState("");
  const [backend, setBackend] = useState(defaultBackend);
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<StepState>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setBackend(defaultBackend);
  }, [defaultBackend]);

  const threadMessages = useMemo(() => {
    const out: ChatMessage[] = [];
    if (topic.trim()) {
      out.push(topicAsUserMessage(topic.trim()));
    }
    for (const node of AGENT_ORDER) {
      const status = steps[node];
      const meta = AGENT_META[node];
      const prevDone = AGENT_ORDER.slice(0, AGENT_ORDER.indexOf(node)).every(
        (n) => steps[n] === "done",
      );
      const isTyping =
        status === "running" ||
        (running && prevDone && status !== "done" && !status);

      if (status === "done") {
        const chars = steps[`${node}_chars`];
        out.push({
          id: node,
          role: meta.role,
          label: meta.label,
          body: chars
            ? `(${chars}자) — 완료 후 대화 탭에서 전문을 볼 수 있습니다.`
            : "완료",
          sent: false,
        });
      } else if (isTyping) {
        out.push({
          id: `${node}-typing`,
          role: meta.role,
          label: meta.label,
          body: "",
          sent: false,
        });
      }
    }
    if (steps.save === "done") {
      out.push({
        id: "save",
        role: "system",
        label: "",
        body: "세션 저장됨",
      });
    }
    return out;
  }, [topic, steps, running]);

  const { scrollRef, showJumpButton, scrollToBottom } = useMessagesScroll(
    [threadMessages, running],
    true,
    "classic-run",
  );

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

  const showThread = running || Object.keys(steps).length > 0;

  return (
    <ChatPaneBody className="chat-pane-body--classic-run">
      <ChatToolbar
        sidebarOpen={sidebarOpen}
        onToggleSidebar={onToggleSidebar}
        title="새 대화"
        meta="Planner → Critic → Scribe"
      />

      <div className="view-tabs-bar">
        <div className="view-tabs-bar__leading">
          <span className="view-tabs-bar__static" aria-hidden>
            대화
          </span>
        </div>
      </div>

      <div className="messages-scroll" ref={scrollRef}>
        {!showThread && !topic.trim() ? (
          <div className="empty-chat">
            주제를 입력하고 보내세요.
            <span className="empty-chat-hint">
              Planner → Critic → Scribe 순서로 실행됩니다
            </span>
          </div>
        ) : (
          threadMessages.map((m) => (
            <div key={m.id} className="chat-line">
              <ChatBubble
                message={m}
                typing={m.id.endsWith("-typing")}
              />
            </div>
          ))
        )}
      </div>

      {error ? <div className="error-banner">{error}</div> : null}

      <ScrollToBottomButton
        visible={showJumpButton}
        onClick={scrollToBottom}
      />

      <ChatComposer
        value={topic}
        onChange={setTopic}
        onSend={handleRun}
        disabled={running}
        placeholder="메시지"
        files={[]}
        onFilesAdd={() => {}}
        onFileRemove={() => {}}
        showAttach={false}
        toolbar={
          <>
            <select
              className="mac-popup execute-composer__select"
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
            <span className="composer-hint">⏎ 전송 · ⇧⏎ 줄바꿈</span>
          </>
        }
      />
    </ChatPaneBody>
  );
}
