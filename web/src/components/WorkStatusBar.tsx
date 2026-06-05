import type { PlanMetaView } from "../utils/planMeta";

export type WorkPhase =
  | "plan_draft"
  | "review_needed"
  | "execute_pending"
  | "merge_verify"
  | "done";

const STEPS: { id: WorkPhase; label: string }[] = [
  { id: "plan_draft", label: "Plan" },
  { id: "review_needed", label: "Review" },
  { id: "execute_pending", label: "Execute" },
  { id: "merge_verify", label: "Verify" },
  { id: "done", label: "Done" },
];

type Props = {
  phase: WorkPhase;
  planMeta: PlanMetaView;
  hasPlan: boolean;
};

export function resolveWorkPhase(input: {
  hasPlan: boolean;
  hasPendingExecution: boolean;
  hasDryRunDiff: boolean;
  pendingAgreement: boolean;
}): WorkPhase {
  if (input.hasPendingExecution) return "execute_pending";
  if (input.hasDryRunDiff || input.pendingAgreement) return "review_needed";
  if (input.hasPlan) return "plan_draft";
  return "plan_draft";
}

export function WorkStatusBar({ phase, planMeta, hasPlan }: Props) {
  const phaseIndex = STEPS.findIndex((s) => s.id === phase);

  return (
    <div className="work-status-bar" role="status">
      <ol className="work-status-bar__steps" aria-label="Work progress">
        {STEPS.map((step, i) => (
          <li
            key={step.id}
            className={[
              "work-status-bar__step",
              i === phaseIndex ? "is-active" : i < phaseIndex ? "is-done" : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            {step.label}
          </li>
        ))}
      </ol>
      {planMeta.freshnessLabel && hasPlan ? (
        <p className="work-status-bar__meta">{planMeta.freshnessLabel}</p>
      ) : null}
    </div>
  );
}
