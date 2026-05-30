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
  highlighted?: boolean;
};

function RoundBadge({ round }: { round: number }) {
  const r = Math.max(1, round);
  return (
    <span className="chat-round-badge" title={`라운드 ${r}`}>
      R{r}
    </span>
  );
}

const ACT_LABELS: Record<string, string> = {
  PROPOSE: "제안",
  AMEND: "수정",
  ENDORSE: "동의",
  CHALLENGE: "이의",
  PASS: "PASS",
  BLOCK: "BLOCK",
};

function ActBadge({ act }: { act: string }) {
  const key = act.toUpperCase();
  return (
    <span className={`chat-act-badge chat-act-badge--${key.toLowerCase()}`} title={`act: ${key}`}>
      {ACT_LABELS[key] ?? key}
    </span>
  );
}

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
  activities?: string[];
};

/** Agent reply in progress — same full-width card as the final response */
export function ReplyWaitingBubble({ agent, label, activities }: ReplyWaitingProps) {
  const who = label?.trim() || agent;
  const lines = activities?.filter(Boolean) ?? [];
  return (
    <article
      className={`chat-turn chat-turn--${agent} chat-turn--waiting`}
      role="status"
      aria-live="polite"
      aria-label={`${who} 답장 중`}
    >
      <header className="chat-turn__head">
        <span className="chat-turn__name">{who}</span>
      </header>
      <div className="chat-turn__body">
        {lines.length > 0 ? (
          <ul className="agent-activity-log" aria-label="진행 중">
            {lines.map((line, i) => (
              <li key={`${line}-${i}`}>{line}</li>
            ))}
          </ul>
        ) : null}
        <TypingIndicator variant="stream" />
      </div>
    </article>
  );
}

export function ChatBubble({ message, typing, highlighted }: Props) {
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
      <article
        className={`chat-turn chat-turn--${role}${highlighted ? " chat-turn--highlight" : ""}`}
      >
        <header className="chat-turn__head">
          <span className="chat-turn__name">{message.label}</span>
          {message.envelope?.act ? <ActBadge act={message.envelope.act} /> : null}
          {(message.parallelRound ?? 1) > 1 ? (
            <RoundBadge round={message.parallelRound ?? 1} />
          ) : null}
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
