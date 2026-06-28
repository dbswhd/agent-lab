import { useEffect, useState } from "react";
import { Avatar } from "./Avatar";
import { ConsoleTurn } from "./ConsoleTurn";
import { HumanSynthesisBubble } from "./HumanSynthesisBubble";
import type { ChatMessage, AgentRole } from "../utils/transcript";
import { parseUserMessageContent } from "../utils/transcript";
import { MessageMarkdown } from "../utils/messageMarkdown";
import { stripAgentReplyBody } from "../utils/agentResponseCard";
import { getTranscriptMarkers } from "../utils/transcriptMessageMarkers";
import {
  TranscriptAuthorLine,
  TranscriptIdentity,
  TranscriptMarkerStrip,
} from "./TranscriptMessageChrome";
import { TurnActivityGroup } from "./TurnActivityGroup";
import { DraftResponseDetails } from "./DraftResponseDetails";
import { formatWorkedDuration } from "../utils/turnTimeline";
import type { TurnItem } from "../utils/turnItems";

const AVATAR_SIZE = 24;

const STREAM_ROLES = new Set<AgentRole>([
  "cursor",
  "codex",
  "claude",
  "kimi",
  "kimi_work",
  "local",
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
  /** Default open state for Draft response (user toggles are remembered). */
  draftDefaultOpen?: boolean;
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

type ReplyWaitingProps = {
  agent: AgentRole;
  label?: string;
  turnItems?: readonly TurnItem[];
  /** Incremental SSE body while agent_token events arrive */
  body?: string;
};

/** Counts seconds up from mount, so a waiting agent never looks frozen even
 *  when its adapter can't stream tokens (e.g. Claude in structured-envelope mode). */
function useElapsedSeconds(): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  return seconds;
}

/** Agent reply in progress — same full-width card as the final response */
export function ReplyWaitingBubble({
  agent,
  label,
  turnItems,
  body,
}: ReplyWaitingProps) {
  const who = label?.trim() || agent;
  const streamText = body?.trim() ?? "";
  const streaming = streamText.length > 0;
  const elapsed = useElapsedSeconds();
  return (
    <ConsoleTurn
      role={agent}
      label={who}
      author={who}
      roleAttr="status"
      ariaLabel={`${who} 답장 중`}
      meta={
        (turnItems?.length ?? 0) > 0 ? undefined : (
          <span className="turn__meta">{formatWorkedDuration(elapsed)}</span>
        )
      }
    >
      <TurnActivityGroup items={turnItems} running />
      {streaming ? (
        <div className="agent-stream-preview">
          <MessageMarkdown text={streamText} variant="transcript" />
        </div>
      ) : null}
      <span className="typing" aria-hidden>
        <span />
        <span />
        <span />
      </span>
    </ConsoleTurn>
  );
}

export function ChatBubble({
  message,
  typing,
  highlighted,
  presentation = "console",
  draftDefaultOpen = false,
}: Props) {
  const sent = message.sent ?? message.role === "you";
  const role = message.role;
  const consoleMode = presentation === "console";

  if (message.humanSynthesis && !typing) {
    return (
      <HumanSynthesisBubble
        message={message}
        highlighted={highlighted}
        presentation={presentation}
      />
    );
  }

  if (role === "system") {
    if (consoleMode) {
      return (
        <div className="transcript-system" role="status">
          {message.body}
        </div>
      );
    }
    return (
      <div className="bubble-row bubble-row--system">
        <span className="bubble bubble--system">{message.body}</span>
      </div>
    );
  }

  if (sent) {
    const parsed = message.attachments?.length
      ? { body: message.body, attachments: message.attachments }
      : parseUserMessageContent(message.body);
    const sentAttachments = parsed.attachments ?? [];
    const sentBody = message.attachments?.length ? message.body : parsed.body;
    const showSentBubble = typing || sentBody.trim().length > 0;

    if (consoleMode) {
      return (
        <div className="bubble-send-block">
          {sentAttachments.length > 0 ? (
            <div className="attachment-bar attachment-bar--sent">
              {sentAttachments.map((name) => (
                <span key={name} className="attachment-chip">
                  <PaperclipIcon />
                  <span className="attachment-chip-name">{name}</span>
                </span>
              ))}
            </div>
          ) : null}
          {showSentBubble ? (
            <div className="bubble-row bubble-row--sent">
              <div className={`bubble-stack bubble-stack--${role}`}>
                <div className="bubble bubble--sent">
                  {typing ? (
                    <TypingIndicator variant="bubble" />
                  ) : (
                    <MessageMarkdown text={sentBody} variant="transcript" />
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </div>
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
                <MessageMarkdown text={sentBody} />
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
    const who = message.label?.trim() || role;
    const draftBody = stripAgentReplyBody(message.body);
    if (consoleMode) {
      return (
        <ConsoleTurn
          role={role}
          label={message.label}
          author={who}
          highlighted={highlighted}
          peer={message.peerChannel}
          chatLineIndex={message.chatLineIndex}
        >
          <TurnActivityGroup items={message.turnItems} running={false} />
          {draftBody ? (
            <DraftResponseDetails
              messageId={message.id}
              body={draftBody}
              defaultOpen={draftDefaultOpen}
            />
          ) : null}
        </ConsoleTurn>
      );
    }
    const transcriptMarkers = getTranscriptMarkers(message);
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
        <div
          className={`mac-bubble mac-bubble--received${typing ? " mac-bubble--typing" : ""}`}
        >
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

function PaperclipIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="m16 6-8.5 8.5a2.12 2.12 0 1 0 3 3L19 9a3.12 3.12 0 1 0-4.4-4.4L9.3 14.3a4.62 4.62 0 1 0 6.5 6.5" />
    </svg>
  );
}
