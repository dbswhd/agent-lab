import type { WorkPhase } from "../utils/workStatusPhase";

const STEPS: { id: WorkPhase; label: string }[] = [
  { id: "plan_draft", label: "Plan" },
  { id: "review_needed", label: "Review" },
  { id: "execute_pending", label: "Execute" },
  { id: "merge_verify", label: "Verify" },
  { id: "done", label: "Done" },
];

type Props = {
  readonly phase: WorkPhase;
  readonly metaLine?: string | null;
};

/** Compact work_phase indicator for the composer event stack. */
export function WorkPhaseChip({ phase, metaLine }: Props) {
  const active = STEPS.find((step) => step.id === phase);
  if (!active) return null;

  return (
    <div
      className="composer-phase-chip"
      role="status"
      aria-label="Work progress"
    >
      <span className="composer-phase-chip__label">{active.label}</span>
      {metaLine ? (
        <span className="composer-phase-chip__meta">{metaLine}</span>
      ) : null}
    </div>
  );
}
