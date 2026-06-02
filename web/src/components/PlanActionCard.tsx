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

export function PlanActionCard({
  n,
  what,
  where,
  verify,
  refs: refsProp,
  onRefClick,
  variant = "default",
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
    ...new Set([
      ...(refsProp ?? []),
      ...whatPart.refs,
      ...wherePart.refs,
      ...verifyPart.refs,
    ]),
  ].sort((a, b) => a - b);

  const card = (
    <div
      className={[
        "plan-doc__action",
        variant === "now" ? "plan-doc__action--now" : "",
        selected ? "is-selected" : "",
        disabled ? "is-disabled" : "",
        selectable ? "is-selectable" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      {...(n != null ? { "data-plan-action-index": String(n) } : {})}
    >
      {(n != null || whatPart.text) && (
        <div className="plan-doc__action-head">
          {n != null ? <span className="plan-doc__action-n">{n}</span> : null}
          {whatPart.text ? (
            <span className="plan-doc__action-what">{renderPlanInline(whatPart.text)}</span>
          ) : null}
        </div>
      )}
      {(wherePart.text || verifyPart.text) && (
        <dl className="plan-doc__action-fields">
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
  );

  if (!selectable) return card;

  return (
    <label className="plan-doc__action-label">
      <input
        type="radio"
        className="plan-doc__action-radio"
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
        "plan-doc__action",
        "plan-doc__action--gate",
        variant === "now" ? "plan-doc__action--now" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="plan-doc__gate">
        <span className="plan-doc__gate-n">{n}</span>
        <span className="plan-doc__text">
          {renderPlanInline(part.text)}
          <PlanDocRefs refs={part.refs} onRefClick={onRefClick} />
        </span>
      </div>
    </div>
  );
}
