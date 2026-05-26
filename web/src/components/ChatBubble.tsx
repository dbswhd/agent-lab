import { Avatar } from "./Avatar";
import type { ChatMessage } from "../utils/transcript";

type Props = {
  message: ChatMessage;
  typing?: boolean;
};

export function ChatBubble({ message, typing }: Props) {
  const sent = message.sent ?? message.role === "you";
  const rowClass = sent ? "bubble-row bubble-row--sent" : "bubble-row bubble-row--received";

  if (message.role === "system") {
    return (
      <div className="bubble-row bubble-row--system">
        <span className="bubble bubble--system">{message.body}</span>
      </div>
    );
  }

  return (
    <div className={rowClass}>
      {!sent && <Avatar role={message.role} label={message.label} />}
      <div className="bubble-stack">
        {!sent && <span className="bubble-sender">{message.label}</span>}
        <div
          className={`bubble bubble--${message.role} ${sent ? "bubble--sent" : "bubble--received"} ${typing ? "bubble--typing" : ""}`}
        >
          {typing ? (
            <span className="typing-dots" aria-label="입력 중">
              <span />
              <span />
              <span />
            </span>
          ) : (
            <div className="bubble-body">{message.body}</div>
          )}
        </div>
      </div>
      {sent && <Avatar role="you" />}
    </div>
  );
}
