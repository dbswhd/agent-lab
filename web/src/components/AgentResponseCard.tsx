import type { ReactNode } from "react";
import { useLocale } from "../i18n/useLocale";
import type { AgentResponseCardFields } from "../utils/agentResponseCard";

type Props = {
  fields: AgentResponseCardFields;
  rawMarkdown: ReactNode;
};

export function AgentResponseCard({ fields, rawMarkdown }: Props) {
  const { msg } = useLocale();
  const hasLists =
    fields.evidence.length > 0 ||
    fields.decisionsNeeded.length > 0 ||
    fields.nextActions.length > 0;

  return (
    <div className="agent-response-card" data-status={fields.status}>
      <div className="agent-response-card__head">
        <span className="agent-response-card__status">{fields.status}</span>
        {fields.summary ? (
          <p className="agent-response-card__summary">{fields.summary}</p>
        ) : null}
      </div>

      {hasLists ? (
        <dl className="agent-response-card__fields">
          {fields.evidence.length > 0 ? (
            <>
              <dt>{msg.responseEvidence}</dt>
              <dd>
                <ul>
                  {fields.evidence.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </dd>
            </>
          ) : null}
          {fields.decisionsNeeded.length > 0 ? (
            <>
              <dt>{msg.responseDecisions}</dt>
              <dd>
                <ul>
                  {fields.decisionsNeeded.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </dd>
            </>
          ) : null}
          {fields.nextActions.length > 0 ? (
            <>
              <dt>{msg.responseNextActions}</dt>
              <dd>
                <ul>
                  {fields.nextActions.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </dd>
            </>
          ) : null}
        </dl>
      ) : null}

      <details className="agent-response-card__raw">
        <summary>{msg.responseRawDisclosure}</summary>
        <div className="agent-response-card__raw-body">{rawMarkdown}</div>
      </details>
    </div>
  );
}
