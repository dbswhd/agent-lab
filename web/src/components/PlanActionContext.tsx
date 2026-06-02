import { MessageMarkdown } from "../utils/messageMarkdown";
import { parsePlanField } from "../utils/planTextFormat";

type FieldProps = {
  label: string;
  value: string | undefined | null;
  onRefClick?: (lineNumber: number) => void;
  compact?: boolean;
};

function PlanActionField({ label, value, onRefClick, compact }: FieldProps) {
  const parsed = parsePlanField(value);
  if (!parsed?.body && !parsed?.refs.length) return null;

  return (
    <div
      className={[
        "plan-action-field",
        compact ? "plan-action-field--compact" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <span className="plan-action-field__label">{label}</span>
      <div className="plan-action-field__content">
        {parsed.body ? (
          <div className="plan-action-field__body">
            <MessageMarkdown text={parsed.body} />
          </div>
        ) : null}
        {parsed.refs.length ? (
          <div className="plan-action-field__refs" aria-label="대화 참조">
            {parsed.refs.map((line) =>
              onRefClick ? (
                <button
                  key={line}
                  type="button"
                  className="plan-action-field__ref plan-action-field__ref--link"
                  title={`대화 L${line}로 이동`}
                  onClick={() => onRefClick(line)}
                >
                  L{line}
                </button>
              ) : (
                <span key={line} className="plan-action-field__ref">
                  L{line}
                </span>
              ),
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}

type Props = {
  where?: string | null;
  verify?: string | null;
  workspaceLabel?: string | null;
  onRefClick?: (lineNumber: number) => void;
  compact?: boolean;
};

export function PlanActionContext({
  where,
  verify,
  workspaceLabel,
  onRefClick,
  compact,
}: Props) {
  const hasWhere = Boolean(parsePlanField(where));
  const hasVerify = Boolean(parsePlanField(verify));
  const hasWorkspace = Boolean(workspaceLabel?.trim());

  if (!hasWhere && !hasVerify && !hasWorkspace) return null;

  return (
    <div
      className={[
        "plan-action-context",
        compact ? "plan-action-context--compact" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <PlanActionField
        label="어디"
        value={where}
        onRefClick={onRefClick}
        compact={compact}
      />
      <PlanActionField
        label="검증"
        value={verify}
        onRefClick={onRefClick}
        compact={compact}
      />
      {hasWorkspace ? (
        <div className="plan-action-field plan-action-field--workspace">
          <span className="plan-action-field__label">workspace</span>
          <span className="plan-action-field__workspace">{workspaceLabel}</span>
        </div>
      ) : null}
    </div>
  );
}
