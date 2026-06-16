import type {
  WorkDecisionActionId,
  WorkDecisionSummary,
} from "../utils/workDecisionTypes";
import { WorkPlanIcon } from "./WorkPlanIcon";

type Props = {
  readonly summary: WorkDecisionSummary;
  readonly onAction: (actionId: WorkDecisionActionId) => void;
};

const KIND_ICON: Record<
  WorkDecisionSummary["kind"],
  "doc" | "alert" | "eyeCheck" | "bolt" | "gitMerge"
> = {
  plan_needed: "doc",
  approval_required: "gitMerge",
  blocked: "alert",
  verifying: "eyeCheck",
  verified: "eyeCheck",
  ready: "bolt",
};

export function WorkDecisionPanel({ summary, onAction }: Props) {
  const secondaryAction =
    summary.secondaryTarget && summary.secondaryLabel
      ? {
          target: summary.secondaryTarget,
          label: summary.secondaryLabel,
        }
      : null;
  return (
    <section
      className={`work-decision work-decision--${summary.kind}`}
      aria-label="Work decision summary"
    >
      <div className="work-decision__main">
        <div className="work-decision__title-row">
          <span className="work-decision__icon" aria-hidden>
            <WorkPlanIcon name={KIND_ICON[summary.kind]} size={16} />
          </span>
          <div>
            <p className="work-decision__eyebrow">{summary.eyebrow}</p>
            <h3 className="work-decision__title">{summary.title}</h3>
          </div>
        </div>
        <p className="work-decision__detail">{summary.detail}</p>
        <dl className="work-decision__facts">
          <div>
            <dt>승인</dt>
            <dd>{summary.whatToApprove}</dd>
          </div>
          <div>
            <dt>막힘</dt>
            <dd>{summary.whyBlocked}</dd>
          </div>
          <div>
            <dt>검증</dt>
            <dd>{summary.verificationStatus}</dd>
          </div>
        </dl>
        <div className="work-decision__actions">
          <button
            type="button"
            className="plan-btn plan-btn--primary plan-btn--compact"
            onClick={() => onAction(summary.primaryTarget)}
          >
            {summary.primaryLabel}
          </button>
          {secondaryAction ? (
            <button
              type="button"
              className="plan-btn plan-btn--compact"
              onClick={() => onAction(secondaryAction.target)}
            >
              {secondaryAction.label}
            </button>
          ) : null}
        </div>
      </div>
      <div className="work-decision__cells">
        {summary.cells.map((cell) => (
          <div
            key={cell.label}
            className={`work-decision-cell work-decision-cell--${cell.state}`}
          >
            <span className="work-decision-cell__label">{cell.label}</span>
            <strong className="work-decision-cell__value">{cell.value}</strong>
            <span className="work-decision-cell__detail">{cell.detail}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
