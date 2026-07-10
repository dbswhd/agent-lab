import type { WorkPhase } from "../utils/workStatusPhase";
import { useLocale } from "../i18n/useLocale";
import { workPhaseLabel } from "../utils/workPhaseLabels";

type Props = {
  readonly phase: WorkPhase;
  readonly metaLine?: string | null;
};

/** Compact work_phase indicator for the composer event stack. */
export function WorkPhaseChip({ phase, metaLine }: Props) {
  const { locale } = useLocale();

  return (
    <div
      className="composer-phase-chip"
      role="status"
      aria-label="Work progress"
    >
      <span className="composer-phase-chip__label">
        {workPhaseLabel(phase, locale)}
      </span>
      {metaLine ? (
        <span className="composer-phase-chip__meta">{metaLine}</span>
      ) : null}
    </div>
  );
}
