import type { ChatMessage } from "../utils/transcript";
import {
  parseHumanSynthesisBody,
  stripHumanSynthesisMarker,
} from "../utils/humanSynthesis";
import { MessageMarkdown } from "../utils/messageMarkdown";
import { useLocale } from "../i18n/useLocale";
import { ConsoleTurn } from "./ConsoleTurn";

type Props = {
  message: ChatMessage;
  highlighted?: boolean;
  presentation?: "console" | "messenger";
};

function agentSlug(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, "-");
}

export function HumanSynthesisBubble({
  message,
  highlighted,
  presentation = "messenger",
}: Props) {
  const { msg } = useLocale();
  const parsed = parseHumanSynthesisBody(message.body);
  const lead = parsed.lead;

  if (presentation === "console") {
    return (
      <ConsoleTurn
        role="scribe"
        className="turn--synthesis"
        author={msg.turnSummary}
        highlighted={highlighted}
        roleAttr="article"
        ariaLabel={msg.turnSummary}
        meta={
          lead ? (
            <span className="turn__meta">lead · {lead}</span>
          ) : undefined
        }
      >
        {parsed.humanExcerpt ? (
          <MessageMarkdown text={parsed.humanExcerpt} variant="transcript" />
        ) : null}
        {parsed.agents.length > 0 ? (
          <ul className="synthesis-console__agents">
            {parsed.agents.map((row) => (
              <li
                key={`${row.name}-${row.summary.slice(0, 24)}`}
                className={`synthesis-console__agent synthesis-console__agent--${agentSlug(row.name)}`}
              >
                <span className="synthesis-console__agent-name">{row.name}</span>
                <span className="synthesis-console__agent-summary">{row.summary}</span>
              </li>
            ))}
          </ul>
        ) : (
          <MessageMarkdown
            text={stripHumanSynthesisMarker(message.body)}
            variant="transcript"
          />
        )}
      </ConsoleTurn>
    );
  }

  return (
    <article
      className={[
        "human-synthesis-bubble",
        highlighted ? "human-synthesis-bubble--highlight" : undefined,
      ]
        .filter(Boolean)
        .join(" ")}
      role="article"
      aria-label={msg.turnSummary}
    >
      <header className="human-synthesis-bubble__head">
        <span className="human-synthesis-bubble__badge">{msg.turnSummary}</span>
        {lead ? (
          <span className="human-synthesis-bubble__lead" title="이번 턴 리드">
            리드 · {lead}
          </span>
        ) : null}
        <span className="human-synthesis-bubble__marker" aria-hidden>
          human synthesis
        </span>
      </header>

      {parsed.humanExcerpt ? (
        <section className="human-synthesis-bubble__section">
          <h3 className="human-synthesis-bubble__section-title">Human</h3>
          <div className="human-synthesis-bubble__excerpt">
            <MessageMarkdown text={parsed.humanExcerpt} />
          </div>
        </section>
      ) : null}

      {parsed.agents.length > 0 ? (
        <section className="human-synthesis-bubble__section">
          <h3 className="human-synthesis-bubble__section-title">에이전트 요약</h3>
          <ul className="human-synthesis-bubble__agents">
            {parsed.agents.map((row) => (
              <li
                key={`${row.name}-${row.summary.slice(0, 24)}`}
                className={`human-synthesis-bubble__agent human-synthesis-bubble__agent--${agentSlug(row.name)}`}
              >
                <span className="human-synthesis-bubble__agent-name">
                  {row.name}
                </span>
                <span className="human-synthesis-bubble__agent-summary">
                  {row.summary}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <div className="human-synthesis-bubble__fallback">
          <MessageMarkdown text={stripHumanSynthesisMarker(message.body)} />
        </div>
      )}
    </article>
  );
}
