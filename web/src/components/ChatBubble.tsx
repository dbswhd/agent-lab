import { Avatar } from "./Avatar";
import { HumanSynthesisBubble } from "./HumanSynthesisBubble";
import type { ChatMessage, AgentRole } from "../utils/transcript";
import { MessageMarkdown } from "../utils/messageMarkdown";
import {
  getTranscriptMarkers,
  TranscriptAuthorLine,
  TranscriptIdentity,
  TranscriptMarkerStrip,
} from "./TranscriptMessageChrome";

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
  /** console = flat transcript log; messenger = legacy iMessage bubbles */
  presentation?: "console" | "messenger";
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
        <TranscriptIdentity label={who} role={agent} />
      </header>
      <div className="chat-turn__body">
        <TranscriptAuthorLine
          message={{
            id: `waiting-${agent}`,
            role: agent,
            label: who,
            body: "",
          }}
        />
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

export function ChatBubble({
  message,
  typing,
  highlighted,
  presentation = "messenger",
}: Props) {
  const sent = message.sent ?? message.role === "you";
  const role = message.role;
  const consoleMode = presentation === "console";

  if (message.humanSynthesis && !typing) {
    return <HumanSynthesisBubble message={message} highlighted={highlighted} />;
  }

  if (role === "system") {
    if (consoleMode) {
      return (
        <p className="transcript-log-line transcript-log-line--system" role="status">
          {message.body}
        </p>
      );
    }
    return (
      <div className="bubble-row bubble-row--system">
        <span className="bubble bubble--system">{message.body}</span>
      </div>
    );
  }

  if (sent) {
    if (consoleMode) {
      return (
        <article
          className={[
            "chat-turn",
            "chat-turn--you",
            highlighted ? "chat-turn--highlight" : undefined,
          ]
            .filter(Boolean)
            .join(" ")}
        >
          <div className="chat-turn__body">
            {typing ? (
              <TypingIndicator variant="stream" />
            ) : (
              <MessageMarkdown text={message.body} />
            )}
          </div>
        </article>
      );
    }

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
    const transcriptMarkers = consoleMode ? getTranscriptMarkers(message) : [];
    return (
      <article
        className={`chat-turn chat-turn--${role}${highlighted ? " chat-turn--highlight" : ""}`}
      >
        <header className="chat-turn__head">
          <TranscriptIdentity label={message.label} role={role} />
        </header>
        <div className="chat-turn__body">
          <TranscriptAuthorLine message={message} />
          <TranscriptMarkerStrip markers={transcriptMarkers} />
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
