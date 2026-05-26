import { useState } from "react";
import type { SessionDetail } from "../api/client";
import { chatLineToMessage, parseTranscript, topicAsUserMessage } from "../utils/transcript";
import { ChatBubble } from "./ChatBubble";
import { ChatPaneBody } from "./ChatPaneBody";
import { ChatToolbar } from "./ChatToolbar";

type Props = {
  session: SessionDetail | null;
  loading: boolean;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
};

export function SessionViewer({
  session,
  loading,
  sidebarOpen,
  onToggleSidebar,
}: Props) {
  const [tab, setTab] = useState<"chat" | "plan">("chat");

  if (loading) {
    return (
      <ChatPaneBody>
        <div className="empty-chat">불러오는 중…</div>
      </ChatPaneBody>
    );
  }

  if (!session) {
    return (
      <ChatPaneBody>
        <div className="empty-chat">
          왼쪽에서 대화를 선택하거나 「새 대화」를 시작하세요.
        </div>
      </ChatPaneBody>
    );
  }

  const messages =
    session.chat && session.chat.length > 0
      ? session.chat.map((line, i) => chatLineToMessage(line, i))
      : [
          topicAsUserMessage(session.topic || session.id),
          ...parseTranscript(session.transcript_md || ""),
        ];

  const workflow =
    (session.run?.workflow_id as string) ||
    (session.meta?.workflow as string) ||
    "session";

  return (
    <ChatPaneBody>
      <ChatToolbar
        sidebarOpen={sidebarOpen}
        onToggleSidebar={onToggleSidebar}
        title={session.topic || session.id}
        meta={workflow}
      />

      <div className="view-tabs-bar" role="tablist">
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

      {tab === "chat" ? (
        <div className="messages-scroll">
          {messages.map((m) => (
            <ChatBubble key={m.id} message={m} />
          ))}
        </div>
      ) : (
        <div className="messages-scroll messages-scroll--document">
          <pre className="plan-pre">{session.plan_md || "(empty)"}</pre>
        </div>
      )}
    </ChatPaneBody>
  );
}
