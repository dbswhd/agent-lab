import { Avatar } from "./Avatar";
import { HumanSynthesisBubble } from "./HumanSynthesisBubble";
import type { ChatMessage, AgentRole } from "../utils/transcript";
import { MessageMarkdown } from "../utils/messageMarkdown";
import {
  actLabel,
  formatEnvelopeMeta,
  normalizeAct,
  shouldWarnMissingEnvelope,
} from "../utils/agentEnvelope";

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

function RoundBadge({ round }: { round: number }) {
  const r = Math.max(1, round);
  return (
    <span className="chat-round-badge" title={`라운드 ${r}`}>
      R{r}
    </span>
  );
}

function ActBadge({ act }: { act: string }) {
  const key = normalizeAct(act);
  const cssKey = (key ?? act).toLowerCase();
  return (
    <span className={`chat-act-badge chat-act-badge--${cssKey}`} title={`act: ${act.toUpperCase()}`}>
      {actLabel(act)}
    </span>
  );
}

function EnvelopeMeta({ envelope }: { envelope: NonNullable<ChatMessage["envelope"]> }) {
  const meta = formatEnvelopeMeta(envelope);
  if (!meta) return null;
  return (
    <span className="chat-envelope-meta" title="envelope refs / confidence">
      {meta}
    </span>
  );
}

function EnvelopeWarning() {
  return (
    <span className="chat-envelope-warn" title="R2+에서는 ```agent-envelope``` JSON fence가 필요합니다">
      envelope 없음
    </span>
  );
}

function getTranscriptMarkers(message: ChatMessage): readonly string[] {
  const act = normalizeAct(message.envelope?.act);
  const refs = message.envelope?.refs ?? [];
  const markers: string[] = [];

  if (act === "BLOCK") {
    markers.push("Review blocker");
  } else if (act === "CHALLENGE") {
    markers.push("Review needed");
  } else if (act === "AMEND" || act === "PROPOSE") {
    markers.push("Plan update");
  }

  if (refs.length > 0) {
    markers.push("Plan ref");
  }

  return markers;
}

function TranscriptMarkerStrip({ markers }: { markers: readonly string[] }) {
  if (markers.length === 0) return null;
  return (
    <div className="transcript-marker-strip" aria-label="Transcript markers">
      {markers.map((marker) => (
        <span key={marker} className="transcript-marker">
          {marker}
        </span>
      ))}
    </div>
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
          <header className="chat-turn__head">
            <span className="chat-turn__name">{message.label ?? "Human"}</span>
          </header>
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
          <span className="chat-turn__name">{message.label}</span>
          {message.envelope?.act ? <ActBadge act={message.envelope.act} /> : null}
          {message.envelope?.act ? <EnvelopeMeta envelope={message.envelope} /> : null}
          {shouldWarnMissingEnvelope(
            message.parallelRound,
            message.envelope,
            message.envelopeParseError,
          ) ? (
            <EnvelopeWarning />
          ) : null}
          {(message.parallelRound ?? 1) > 1 ? (
            <RoundBadge round={message.parallelRound ?? 1} />
          ) : null}
        </header>
        <div className="chat-turn__body">
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
