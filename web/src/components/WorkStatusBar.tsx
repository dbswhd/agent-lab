import type { WorkPhase } from "../utils/workStatusPhase";

const STEPS: { id: WorkPhase; label: string }[] = [
  { id: "plan_draft", label: "Plan" },
  { id: "review_needed", label: "Review" },
  { id: "execute_pending", label: "Execute" },
  { id: "merge_verify", label: "Verify" },
  { id: "done", label: "Done" },
];

type Props = {
  phase: WorkPhase;
  metaLine: string | null;
  hasPlan: boolean;
  /** Mission loop paused — show badge; stepper uses resume phase when set. */
  missionPaused?: boolean;
  /** MB-2 — call budget usage (distinct from context token budget). */
  budgetPct?: number;
};

export function WorkStatusBar({
  phase,
  metaLine,
  hasPlan,
  missionPaused = false,
  budgetPct = 0,
}: Props) {
  const phaseIndex = STEPS.findIndex((s) => s.id === phase);

  return (
    <div
      className={[
        "work-status-bar",
        missionPaused ? "work-status-bar--paused" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      role="status"
    >
      {missionPaused ? (
        <span
          className="work-status-bar__pause-badge"
          aria-label="Mission paused"
        >
          Paused
        </span>
      ) : null}
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
      {budgetPct > 0 ? (
        <div
          className="work-status-bar__budget"
          role="meter"
          aria-valuenow={budgetPct}
          aria-valuemin={0}
          aria-valuemax={100}
          title={`Call budget ${budgetPct}%`}
        >
          <span className="work-status-bar__budget-label">Budget</span>
          <span
            className="work-status-bar__budget-fill"
            style={{ width: `${Math.min(100, budgetPct)}%` }}
          />
          <span className="work-status-bar__budget-pct">{budgetPct}%</span>
        </div>
      ) : null}
      {metaLine && hasPlan ? (
        <p className="work-status-bar__meta">{metaLine}</p>
      ) : null}
    </div>
  );
}
