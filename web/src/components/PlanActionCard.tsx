import { parsePlanField } from "../utils/planTextFormat";
import { PlanDocRefs, renderPlanInline } from "../utils/planDocInline";

type Props = {
  n?: number;
  what?: string | null;
  where?: string | null;
  verify?: string | null;
  refs?: number[];
  onRefClick?: (line: number) => void;
  variant?: "now" | "default";
  recommended?: boolean;
  selected?: boolean;
  disabled?: boolean;
  selectable?: boolean;
  radioName?: string;
  checked?: boolean;
  onSelect?: () => void;
};

function fieldBody(value: string | undefined | null): { text: string; refs: number[] } {
  const parsed = parsePlanField(value);
  return { text: parsed?.body ?? "", refs: parsed?.refs ?? [] };
}

/**
 * Rebuilt plan action card. ALL behavior preserved: ref aggregation,
 * selectable radio wrapper, now/gate variants. New `.plan-action` classes.
 */
export function PlanActionCard({
  n,
  what,
  where,
  verify,
  refs: refsProp,
  onRefClick,
  variant = "default",
  recommended,
  selected,
  disabled,
  selectable,
  radioName,
  checked,
  onSelect,
}: Props) {
  const whatPart = fieldBody(what);
  const wherePart = fieldBody(where);
  const verifyPart = fieldBody(verify);
  const refs = [
    ...new Set([...(refsProp ?? []), ...whatPart.refs, ...wherePart.refs, ...verifyPart.refs]),
  ].sort((a, b) => a - b);

  const card = (
    <div
      className={[
        "plan-action",
        variant === "now" ? "plan-action--now" : "",
        recommended ? "plan-action--recommended" : "",
        selected ? "is-selected" : "",
        disabled ? "is-disabled" : "",
        selectable ? "is-selectable" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      {...(n != null ? { "data-plan-action-index": String(n) } : {})}
    >
      {n != null ? <span className="plan-action__index">{n}</span> : null}
      <div className="plan-action__main">
        {whatPart.text ? (
          <span className="plan-action__what">{renderPlanInline(whatPart.text)}</span>
        ) : null}
        {(wherePart.text || verifyPart.text) && (
          <dl className="plan-action__fields">
            {wherePart.text ? (
              <>
                <dt>어디</dt>
                <dd>{renderPlanInline(wherePart.text)}</dd>
              </>
            ) : null}
            {verifyPart.text ? (
              <>
                <dt>검증</dt>
                <dd>{renderPlanInline(verifyPart.text)}</dd>
              </>
            ) : null}
          </dl>
        )}
        <PlanDocRefs refs={refs} onRefClick={onRefClick} />
      </div>
    </div>
  );

  if (!selectable) return card;

  return (
    <label className="plan-action-label">
      <input
        type="radio"
        className="plan-action-radio"
        name={radioName}
        checked={checked}
        disabled={disabled}
        onChange={onSelect}
      />
      {card}
    </label>
  );
}

export function PlanGateLine({
  n,
  text,
  onRefClick,
  variant = "default",
}: {
  n: number;
  text: string;
  onRefClick?: (line: number) => void;
  variant?: "now" | "default";
}) {
  const part = fieldBody(text);
  return (
    <div
      className={[
        "plan-action",
        "plan-action--gate",
        variant === "now" ? "plan-action--now" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <span className="plan-action__index plan-action__index--gate">{n}</span>
      <span className="plan-action__main">
        {renderPlanInline(part.text)}
        <PlanDocRefs refs={part.refs} onRefClick={onRefClick} />
      </span>
    </div>
  );
}
