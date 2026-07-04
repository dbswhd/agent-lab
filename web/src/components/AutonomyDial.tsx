import type { AutonomySessionView } from "../utils/autonomyLadder";
import { autonomyLevelLabel } from "../utils/autonomyLadder";
import { useLocale } from "../i18n/useLocale";

type Props = {
  readonly view: AutonomySessionView | null;
  readonly loading?: boolean;
};

/** N4: session header autonomy level + trust budget chip. */
export function AutonomyDial({ view, loading }: Props) {
  const { locale } = useLocale();
  if (!view && !loading) return null;

  const level = view?.displayLevel ?? "L0";
  const label = autonomyLevelLabel(level, locale);
  const title = view?.summary ?? (loading ? "…" : label);

  return (
    <span
      className={`workspace-chrome__pill workspace-chrome__pill--autonomy workspace-chrome__pill--${level.toLowerCase()}`}
      title={title}
      aria-label={
        locale === "ko"
          ? `자율도 ${label}${view && view.trustBudgetTotal > 0 ? `, trust ${view.trustBudgetRemaining}/${view.trustBudgetTotal}` : ""}`
          : `Autonomy ${label}${view && view.trustBudgetTotal > 0 ? `, trust ${view.trustBudgetRemaining}/${view.trustBudgetTotal}` : ""}`
      }
    >
      <span className="autonomy-dial__level">{level}</span>
      <span className="autonomy-dial__label">{label}</span>
      {view && view.trustBudgetTotal > 0 ? (
        <span className="autonomy-dial__budget">
          {view.trustBudgetRemaining}/{view.trustBudgetTotal}
        </span>
      ) : null}
    </span>
  );
}
