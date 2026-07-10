import type { WorkPhase } from "../utils/workStatusPhase";
import { useLocale } from "../i18n/useLocale";
import { WORK_PHASE_LABELS } from "../utils/workPhaseLabels";
import { workStepStatusClass } from "../utils/workStepClass";

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
  const { locale } = useLocale();
  const phaseIndex = WORK_PHASE_LABELS.findIndex((step) => step.id === phase);

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
        {WORK_PHASE_LABELS.map((step, i) => (
          <li
            key={step.id}
            className={[
              "work-status-bar__step",
              workStepStatusClass(i, phaseIndex),
            ]
              .filter(Boolean)
              .join(" ")}
          >
            {locale === "ko" ? step.ko : step.en}
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
