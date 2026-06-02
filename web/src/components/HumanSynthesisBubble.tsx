import type { ChatMessage } from "../utils/transcript";
import {
  parseHumanSynthesisBody,
  stripHumanSynthesisMarker,
} from "../utils/humanSynthesis";
import { MessageMarkdown } from "../utils/messageMarkdown";

type Props = {
  message: ChatMessage;
  highlighted?: boolean;
};

function agentSlug(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, "-");
}

export function HumanSynthesisBubble({ message, highlighted }: Props) {
  const parsed = parseHumanSynthesisBody(message.body);
  const lead = parsed.lead;

  return (
    <article
      className={[
        "human-synthesis-bubble",
        highlighted ? "human-synthesis-bubble--highlight" : undefined,
      ]
        .filter(Boolean)
        .join(" ")}
      role="article"
      aria-label="턴 요약"
    >
      <header className="human-synthesis-bubble__head">
        <span className="human-synthesis-bubble__badge">턴 요약</span>
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
          <MessageMarkdown
            text={stripHumanSynthesisMarker(message.body)}
          />
        </div>
      )}
    </article>
  );
}
