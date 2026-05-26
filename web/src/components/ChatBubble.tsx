import { Avatar } from "./Avatar";
import type { ChatMessage, AgentRole } from "../utils/transcript";
import { MessageMarkdown } from "../utils/messageMarkdown";

const AVATAR_SIZE = 24;

const STREAM_ROLES = new Set<AgentRole>([
  "cursor",
  "codex",
  "claude",
  "planner",
  "critic",
  "scribe",
]);

type Props = {
  message: ChatMessage;
  typing?: boolean;
};

function TypingIndicator({ variant }: { variant: "bubble" | "stream" }) {
  return (
    <span
      className={`typing-dots${variant === "stream" ? " typing-dots--stream" : ""}`}
      aria-hidden
    >
      <span />
      <span />
      <span />
    </span>
  );
}

const REPLY_WAIT_ROLES = new Set<AgentRole>([
  "cursor",
  "codex",
  "claude",
  "planner",
  "critic",
  "scribe",
]);

export function isReplyWaitRole(role: AgentRole): boolean {
  return REPLY_WAIT_ROLES.has(role);
}

type ReplyWaitingProps = {
  agent: AgentRole;
  label?: string;
};

/** Compact typing bubble tinted like the agent's chat-turn card */
export function ReplyWaitingBubble({ agent, label }: ReplyWaitingProps) {
  const who = label?.trim() || agent;
  return (
    <div
      className="bubble-row bubble-row--received bubble-row--reply-wait"
      role="status"
      aria-live="polite"
      aria-label={`${who} 답장 중`}
    >
      <div
        className={`mac-bubble mac-bubble--received mac-bubble--typing mac-bubble--agent-${agent}`}
      >
        <TypingIndicator variant="bubble" />
      </div>
    </div>
  );
}

export function ChatBubble({ message, typing }: Props) {
  const sent = message.sent ?? message.role === "you";
  const role = message.role;

  if (role === "system") {
    return (
      <div className="bubble-row bubble-row--system">
        <span className="bubble bubble--system">{message.body}</span>
      </div>
    );
  }

  if (sent) {
    const bubbleClass = [
      "mac-bubble",
      "mac-bubble--sent",
      typing ? "mac-bubble--typing" : "",
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <div className="bubble-row bubble-row--sent">
        <div className="bubble-stack">
          <span className="bubble-sender">{message.label}</span>
          <div className={bubbleClass}>
            {typing ? (
              <TypingIndicator variant="bubble" />
            ) : (
              <div className="bubble-body">
                <MessageMarkdown text={message.body} />
              </div>
            )}
          </div>
        </div>
        <Avatar role="you" size={AVATAR_SIZE} />
      </div>
    );
  }

  if (STREAM_ROLES.has(role)) {
    if (typing) return null;
    return (
      <article className={`chat-turn chat-turn--${role}`}>
        <header className="chat-turn__head">
          <span className="chat-turn__name">{message.label}</span>
        </header>
        <div className="chat-turn__body">
          <MessageMarkdown text={message.body} />
        </div>
      </article>
    );
  }

  return (
    <div className="bubble-row bubble-row--received">
      <Avatar role={role} label={message.label} size={AVATAR_SIZE} />
      <div className="bubble-stack">
        <span className="bubble-sender">{message.label}</span>
        <div className={`mac-bubble mac-bubble--received${typing ? " mac-bubble--typing" : ""}`}>
          {typing ? (
            <TypingIndicator variant="bubble" />
          ) : (
            <div className="bubble-body">
              <MessageMarkdown text={message.body} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
